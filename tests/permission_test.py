"""权限与越权测试（一期地基验收）

覆盖：
- 未登录 / token 失效 → 401
- 客户账号访问管理端接口 → 403，且响应里不出现他人信息
- 客户访问他人订单 → 404（不泄露"这单存在"）
- 客户端接口不接受手机号参数，传了也只返回本人数据
- 员工账号访问客户端接口 → 403
- 两个登录口互不通用
- 注册冲突 → 409

运行：python tests/permission_test.py
测试在临时数据库副本上运行，不会污染 laundry.db
"""
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

SRC_DB = os.path.join(BASE_DIR, "laundry.db")
TMP_DB = os.path.join(tempfile.gettempdir(), "laundry_permission.db")
if os.path.exists(TMP_DB):
    os.remove(TMP_DB)
shutil.copy(SRC_DB, TMP_DB)
os.environ["LAUNDRY_DATABASE_URL"] = "sqlite:///" + TMP_DB.replace("\\", "/")

import jwt  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import ALGORITHM, SECRET_KEY  # noqa: E402
from app.main import app  # noqa: E402

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond), extra))


# 客户 A = 老客户 lk（手机 123456，历史订单 1/2/6/12）
# 客户 B = 老客户 hch（手机 147258，历史订单 4）
PHONE_A, PHONE_B = "123456", "147258"
ORDER_B_ID = 4
ORDER_B_NO = "O20260604181055"

with TestClient(app) as c:
    # ---------- 1. 未登录 ----------
    check("未登录访问订单接口 401", c.get("/api/orders").status_code == 401)
    check("未登录访问客户端接口 401", c.get("/api/my/orders").status_code == 401)
    check("伪造 token 401", c.get("/api/orders", headers={"Authorization": "Bearer abc.def.ghi"}).status_code == 401)
    check("篡改签名 401", c.get("/api/orders", headers={"Authorization": "Bearer " + jwt.encode(
        {"sub": "1", "role": "admin", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "wrong-secret", algorithm=ALGORITHM)}).status_code == 401)
    check("过期 token 401", c.get("/api/orders", headers={"Authorization": "Bearer " + jwt.encode(
        {"sub": "1", "role": "admin", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        SECRET_KEY, algorithm=ALGORITHM)}).status_code == 401)

    # ---------- 2. 员工登录仍然正常 ----------
    r = c.post("/api/login", json={"username": "admin", "password": "admin123"})
    admin_token = r.json().get("token", "")
    AH = {"Authorization": "Bearer " + admin_token}
    check("管理员登录成功", r.status_code == 200 and bool(admin_token))
    check("管理员可访问管理端订单", c.get("/api/orders", headers=AH).status_code == 200)

    # ---------- 3. 客户注册 / 登录 ----------
    # P0-3：老客户手机号不再允许自助"认领"，必须由门店开通账号
    r = c.post("/api/customer/register", json={"phone": PHONE_A, "password": "pass1234"})
    check("老客户手机号自助注册被拦（409）", r.status_code == 409, str(r.json())[:200])

    # 门店给 A、B 开通账号（这是唯一能绑定历史档案的入口）
    from app.db import SessionLocal  # noqa: E402
    from app.models import Customer  # noqa: E402

    db = SessionLocal()
    id_a = db.query(Customer).filter(Customer.phone == PHONE_A).first().id
    id_b = db.query(Customer).filter(Customer.phone == PHONE_B).first().id
    db.close()
    r = c.post("/api/customers/" + str(id_a) + "/bind-account", json={"phone": PHONE_A, "password": "pass1234"}, headers=AH)
    check("门店为老客户 A 开通账号", r.status_code == 200, str(r.json())[:200])
    check("开通响应不含密码", "password" not in str(r.json()))

    r = c.post("/api/customer/register", json={"phone": PHONE_A, "password": "pass1234"})
    check("已开通的账号再自助注册 409", r.status_code == 409, str(r.json()))

    r = c.post("/api/customers/" + str(id_b) + "/bind-account", json={"phone": PHONE_B, "password": "pass5678"}, headers=AH)
    check("门店为老客户 B 开通账号", r.status_code == 200, str(r.json())[:200])

    # 新客户（库里没有档案）可以自助注册
    r = c.post("/api/customer/register", json={"phone": "13900009999", "password": "pass9999"})
    check("全新手机号可自助注册", r.status_code == 200, str(r.json())[:200])
    check("自助注册不绑他人档案", r.json().get("existing_archive") is False)

    r = c.post("/api/customer/login", json={"phone": PHONE_A, "password": "pass1234"})
    token_a = r.json().get("token", "")
    A = {"Authorization": "Bearer " + token_a}
    check("客户登录成功且 role=customer", r.status_code == 200 and r.json()["user"]["role"] == "customer")

    r = c.post("/api/customer/login", json={"phone": PHONE_B, "password": "pass5678"})
    token_b = r.json().get("token", "")
    B = {"Authorization": "Bearer " + token_b}

    r = c.post("/api/customer/login", json={"phone": PHONE_A, "password": "wrong"})
    check("客户错误密码 401", r.status_code == 401)

    # ---------- 4. 两个登录口互不通用 ----------
    r = c.post("/api/login", json={"username": PHONE_A, "password": "pass1234"})
    check("客户账号走管理端登录口被拒 403", r.status_code == 403, str(r.json()))
    r = c.post("/api/customer/login", json={"phone": "admin", "password": "admin123"})
    check("员工账号走客户端登录口被拒 401", r.status_code == 401, str(r.json()))

    # ---------- 5. 客户访问管理端接口一律 403 ----------
    admin_apis = [
        ("GET", "/api/orders"),
        ("GET", "/api/stats"),
        ("GET", "/api/customers"),
        ("GET", "/api/members"),
        ("GET", "/api/inventory"),
        ("GET", "/api/services"),
        ("GET", "/api/orders/overdue"),
    ]
    for method, url in admin_apis:
        r = c.get(url, headers=A)
        check(f"客户访问 {url} 被拒 403", r.status_code == 403, f"{r.status_code} {str(r.json())[:120]}")
        # 403 响应体不得带出他人信息
        body = str(r.json())
        check(f"{url} 的 403 响应不泄露他人姓名/手机号", ("hch" not in body and "147258" not in body))

    r = c.post("/api/orders", json={
        "customer_name": "越权测试", "customer_phone": "13900009999",
        "items_detail": [{"category": "上衣", "service_name": "普通洗", "quantity": 1}],
    }, headers=A)
    check("客户不能建单 403", r.status_code == 403, str(r.json()))

    r = c.post(f"/api/orders/{ORDER_B_ID}/complete", headers=A)
    check("客户不能结算订单 403", r.status_code == 403, str(r.json()))

    # ---------- 6. 员工访问客户端接口 403 ----------
    for url in ("/api/my/profile", "/api/my/orders", "/api/my/summary"):
        r = c.get(url, headers=AH)
        check(f"员工访问 {url} 被拒 403", r.status_code == 403, f"{r.status_code} {str(r.json())[:120]}")

    # ---------- 7. 只返回本人数据 ----------
    r = c.get("/api/my/orders", headers=A)
    rows = r.json().get("data", []) if r.status_code == 200 else []
    nos = [o["order_no"] for o in rows]
    check("客户 A 能看到自己的历史订单", len(rows) > 0 and "O20260604155228" in nos, f"{len(rows)} 单")
    check("客户 A 看不到客户 B 的订单", ORDER_B_NO not in nos, str(nos))
    check("客户 A 的列表里没有客户 B 的手机号", "147258" not in str(r.json()))

    r = c.get("/api/my/orders", headers=B)
    nos_b = [o["order_no"] for o in (r.json().get("data", []) if r.status_code == 200 else [])]
    check("客户 B 只看到自己的单", ORDER_B_NO in nos_b and "O20260604155228" not in nos_b, str(nos_b))

    # ---------- 8. 跨客户访问他人订单 → 404（不泄露存在性） ----------
    r = c.get(f"/api/my/orders/{ORDER_B_ID}", headers=A)
    check("客户 A 查客户 B 的订单 404", r.status_code == 404, f"{r.status_code} {str(r.json())[:120]}")
    check("越权 404 响应不泄露订单号", ORDER_B_NO not in str(r.json()) and "147258" not in str(r.json()))

    r = c.get(f"/api/my/orders/{ORDER_B_ID}", headers=B)
    check("客户 B 查自己的订单 200", r.status_code == 200, str(r.status_code))

    # ---------- 9. 客户端接口不接受手机号参数 ----------
    r = c.get("/api/my/orders?phone=" + PHONE_B, headers=A)
    nos_spoof = [o["order_no"] for o in (r.json().get("data", []) if r.status_code == 200 else [])]
    check("传 phone 参数查不到他人订单", ORDER_B_NO not in nos_spoof, str(nos_spoof))
    check("传 customer_id 参数也无效", ORDER_B_NO not in str(
        c.get(f"/api/my/orders?customer_id=4&id={ORDER_B_ID}", headers=A).json()))

    r = c.get("/api/my/profile", headers=A)
    check("我的资料只含本人手机号", r.status_code == 200 and r.json()["data"]["phone"] == PHONE_A, str(r.json())[:160])

    # ---------- 10. 摘要金额口径 ----------
    r = c.get("/api/my/summary", headers=A)
    d = r.json().get("data", {})
    check("摘要含待付款/累计消费字段", all(k in d for k in ("unpaid_amount", "total_spent", "active_count", "ready_count")), str(d)[:200])
    check("摘要里的订单总数与列表一致", d.get("total_orders") == len(rows), f"{d.get('total_orders')} vs {len(rows)}")

    # ---------- 11. 客户端页面可访问（数据由接口守护） ----------
    check("客户登录页 200", c.get("/me/login").status_code == 200)
    check("客户首页 200", c.get("/me").status_code == 200)
    check("客户订单页 200", c.get("/me/orders").status_code == 200)
    check("me.css 可用", c.get("/css/me.css").status_code == 200)
    check("me.js 可用", c.get("/js/me.js").status_code == 200)
    check("me_common.js 可用", c.get("/js/me_common.js").status_code == 200)

passed = sum(1 for _, ok, _ in results if ok)
print("=" * 60)
for name, ok, extra in results:
    print(("PASS " if ok else "FAIL ") + name + (("  <- " + extra) if (extra and not ok) else ""))
print("=" * 60)
print(f"通过 {passed} / {len(results)}")
sys.exit(0 if passed == len(results) else 1)
