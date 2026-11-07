"""回填历史订单明细：把旧订单的 items 文本解析成 order_items 结构化行

用法：python scripts/migrate_order_items.py
可安全重复执行（已有明细的订单会跳过）
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Order, OrderItem  # noqa: E402
from app.services.order_service import parse_items_text  # noqa: E402


def main() -> None:
    db = SessionLocal()
    filled = 0
    skipped = 0
    try:
        for order in db.execute(select(Order)).scalars().all():
            existing = db.execute(select(OrderItem).where(OrderItem.order_id == order.id)).scalars().first()
            if existing:
                skipped += 1
                continue
            rows = parse_items_text(order.items or "")
            if not rows:
                continue
            for row in rows:
                db.add(OrderItem(order_id=order.id, **row))
            filled += 1
        db.commit()
        print("回填订单数：" + str(filled) + "，已存在跳过：" + str(skipped))
    finally:
        db.close()


if __name__ == "__main__":
    main()
