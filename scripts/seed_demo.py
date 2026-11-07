# -*- coding: utf-8 -*-
"""部署/演示用的初始化数据（幂等，可反复跑）

线上第一启动时数据库是空的：表会由 create_all 建出来，但没有价目表、没有分类、
没有耗材，客户一进「线上点单」就会看到"暂无服务项目"。这个脚本补齐这些，并把
初始管理员密码换成随机值（公网别用 admin123）。

用法：
  python scripts/seed_demo.py                        # 建价目/分类/耗材 + 演示客户，管理员密码随机
  python scripts/seed_demo.py --admin-password xxx    # 指定管理员密码
  python scripts/seed_demo.py --no-demo-customer      # 不建演示客户
"""
import argparse
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal, engine  # noqa: E402
from app.models import Base, Category, Customer, Inventory, ServiceItem, User  # noqa: E402
from app.services.auth_service import bind_account  # noqa: E402
from app.security import hash_password  # noqa: E402

CATEGORIES = [
    ("上衣", "各类上衣"),
    ("裤子", "各类裤子"),
    ("外套", "各类外套"),
    ("内衣", "各类内衣"),
    ("家纺", "床上用品"),
]

SERVICES = [
    ("普通洗", 20.0, "件", "水洗", "日常水洗，棉麻衬衫、T 恤"),
    ("干洗", 35.0, "件", "干洗", "西装、大衣、羊毛羊绒"),
    ("熨烫", 10.0, "件", "熨烫", "只熨烫不水洗"),
    ("消毒", 15.0, "件", "消毒", "母婴、贴身衣物加消毒"),
    ("精洗", 50.0, "件", "水洗", "手洗精护，蕾丝、真丝、羽绒"),
]

DEMO_PHONE = "13800138000"
DEMO_PASSWORD = "demo1234"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admin-password", default="")
    parser.add_argument("--no-demo-customer", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    Base.metadata.create_all(bind=engine)  # 空库第一次跑也能直接建表
    created = {"category": 0, "service": 0, "inventory": 0}

    for name, desc in CATEGORIES:
        if not db.query(Category).filter(Category.name == name).first():
            db.add(Category(name=name, description=desc))
            created["category"] += 1

    for name, price, unit, category, desc in SERVICES:
        if not db.query(ServiceItem).filter(ServiceItem.name == name).first():
            db.add(ServiceItem(name=name, price=price, unit=unit, category=category, description=desc))
            created["service"] += 1

    if not db.query(Inventory).filter(Inventory.name == "洗涤耗材").first():
        db.add(Inventory(name="洗涤耗材", quantity=100, unit="件", price=0))
        created["inventory"] += 1

    db.commit()

    # 管理员密码：公网部署不要用 admin123
    admin = db.query(User).filter(User.role == "admin").first()
    admin_password = args.admin_password or secrets.token_urlsafe(12)
    if admin:
        admin.password = hash_password(admin_password)
        db.commit()
        print(f"管理员账号：{admin.username} / 密码：{admin_password}（只显示这一次，请记下来）")
    else:
        db.add(User(username="admin", password=hash_password(admin_password), role="admin", name="管理员"))
        db.commit()
        print(f"已创建管理员：admin / {admin_password}")

    if not args.no_demo_customer:
        customer = db.query(Customer).filter(Customer.phone == DEMO_PHONE).first()
        if not customer:
            customer = Customer(name="演示客户", phone=DEMO_PHONE, address="演示地址", points=0, member_level=0)
            db.add(customer)
            db.commit()
            db.refresh(customer)
        try:
            bind_account(db, customer.id, DEMO_PHONE, DEMO_PASSWORD, customer.name)
            print(f"演示客户：{DEMO_PHONE} / {DEMO_PASSWORD}（可在客户端登录看订单）")
        except Exception as exc:  # 已绑定就跳过
            print(f"演示客户账号已存在或跳过：{type(exc).__name__} {exc}")

    print(
        "初始化完成：分类 +{category}、服务项目 +{service}、耗材 +{inventory}".format(**created)
    )
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
