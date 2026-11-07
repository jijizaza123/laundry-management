"""验收：确认数据未被破坏，且结构化明细可用于统计"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from sqlalchemy import func, select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Customer, Order, OrderItem, Transaction  # noqa: E402
from app.services import stats_service  # noqa: E402

db = SessionLocal()
print("customers =", db.execute(select(func.count()).select_from(Customer)).scalar())
print("orders    =", db.execute(select(func.count()).select_from(Order)).scalar())
print("transactions =", db.execute(select(func.count()).select_from(Transaction)).scalar())
print("order_items  =", db.execute(select(func.count()).select_from(OrderItem)).scalar())
print()
print("服务项目排行：")
for row in stats_service.service_ranking(db, limit=10):
    print("  ", row)

print()
print("近 8 单明细示例：")
for o in db.execute(select(Order).order_by(Order.id.desc()).limit(8)).scalars().all():
    print("  ", o.order_no, o.status, "->", [(i.category, i.service_name, i.quantity) for i in o.item_rows])
db.close()
