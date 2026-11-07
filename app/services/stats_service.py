"""统计业务：首页看板、日报、区间报表、财务流水"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import (
    ACTIVE_STATUSES,
    ORDER_STATUS_COMPLETED,
    ORDER_STATUS_READY,
    ORDER_STATUS_RECEIVED,
    ORDER_STATUS_WASHING,
)
from ..models import Customer, Order, Transaction, now_str
from ..exceptions import ConflictError


def add_transaction(
    db: Session,
    type_: str,
    amount: float,
    description: str = "",
    order_id: int | None = None,
    staff_id: int = 1,
) -> dict:
    if type_ not in ("income", "expense"):
        raise ConflictError("流水类型只能是 income 或 expense")
    if float(amount) <= 0:
        raise ConflictError("金额必须大于 0")
    t = Transaction(
        order_id=order_id,
        type=type_,
        amount=round(float(amount), 2),
        description=description,
        staff_id=staff_id,
        transaction_time=now_str(),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return {
        "id": t.id,
        "order_id": t.order_id,
        "type": t.type,
        "amount": t.amount,
        "description": t.description,
        "transaction_time": t.transaction_time,
    }


def _sum_amount(db: Session, tx_type: str, date_prefix: str | None = None) -> float:
    stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.type == tx_type)
    if date_prefix:
        stmt = stmt.where(func.substr(Transaction.transaction_time, 1, 10) == date_prefix)
    return round(float(db.execute(stmt).scalar() or 0), 2)


def dashboard(db: Session) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    today_orders = db.execute(
        select(func.count()).select_from(Order).where(func.substr(Order.receive_time, 1, 10) == today)
    ).scalar()
    total_customers = db.execute(select(func.count()).select_from(Customer)).scalar()

    counts = {}
    for status in (ORDER_STATUS_RECEIVED, ORDER_STATUS_WASHING, ORDER_STATUS_READY):
        counts[status] = int(
            db.execute(select(func.count()).select_from(Order).where(Order.status == status)).scalar() or 0
        )

    in_store = sum(counts.values())
    ready_count = counts[ORDER_STATUS_READY]

    # 逾期未取：预计取衣日期已过且仍在店内
    overdue_rows = db.execute(
        select(Order).where(Order.status.in_(ACTIVE_STATUSES), Order.expected_pickup.is_not(None))
    ).scalars().all()
    overdue_count = len([o for o in overdue_rows if (o.expected_pickup or "")[:10] < today])

    total_income = _sum_amount(db, "income")
    total_expense = _sum_amount(db, "expense")
    today_income = _sum_amount(db, "income", today)

    return {
        "date": today,
        "today_orders": int(today_orders or 0),
        "in_store": in_store,
        "received_count": counts[ORDER_STATUS_RECEIVED],
        "washing_count": counts[ORDER_STATUS_WASHING],
        "ready_count": ready_count,
        "overdue_count": overdue_count,
        "total_income": total_income,
        "total_expense": total_expense,
        "total_customers": int(total_customers or 0),
        "today_income": today_income,
        "net_profit": round(total_income - total_expense, 2),
        # 兼容旧首页字段
        "pending_orders": in_store,
    }


def trend(db: Session, days: int = 7) -> list[dict]:
    """近 N 天的订单量与收入趋势，用于首页柱状图"""
    days = max(1, min(int(days), 60))
    result = []
    today = datetime.now()
    for offset in range(days - 1, -1, -1):
        d = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        order_count = int(
            db.execute(
                select(func.count()).select_from(Order).where(func.substr(Order.receive_time, 1, 10) == d)
            ).scalar()
            or 0
        )
        income = _sum_amount(db, "income", d)
        result.append({"date": d, "label": d[5:], "order_count": order_count, "income": income})
    return result



def daily_report(db: Session, date: str | None = None) -> dict:
    date = date or datetime.now().strftime("%Y-%m-%d")
    order_count = db.execute(
        select(func.count()).select_from(Order).where(func.substr(Order.receive_time, 1, 10) == date)
    ).scalar()
    received_amount = round(
        float(
            db.execute(
                select(func.coalesce(func.sum(Order.total_price), 0)).where(
                    func.substr(Order.receive_time, 1, 10) == date
                )
            ).scalar()
            or 0
        ),
        2,
    )
    income = _sum_amount(db, "income", date)
    expense = _sum_amount(db, "expense", date)
    completed = db.execute(
        select(func.count())
        .select_from(Order)
        .where(func.substr(Order.actual_pickup, 1, 10) == date, Order.status == ORDER_STATUS_COMPLETED)
    ).scalar()
    return {
        "date": date,
        "order_count": int(order_count or 0),
        "completed_count": int(completed or 0),
        "total_received": received_amount,
        "total_income": income,
        "total_expense": expense,
        "net_profit": round(income - expense, 2),
    }


def range_report(db: Session, start_date: str, end_date: str) -> dict:
    """按日期区间统计，日期格式 YYYY-MM-DD"""
    prefix_start = start_date[:10]
    prefix_end = end_date[:10]
    order_count = db.execute(
        select(func.count())
        .select_from(Order)
        .where(func.substr(Order.receive_time, 1, 10) >= prefix_start, func.substr(Order.receive_time, 1, 10) <= prefix_end)
    ).scalar()
    total_price = round(
        float(
            db.execute(
                select(func.coalesce(func.sum(Order.total_price), 0)).where(
                    func.substr(Order.receive_time, 1, 10) >= prefix_start,
                    func.substr(Order.receive_time, 1, 10) <= prefix_end,
                )
            ).scalar()
            or 0
        ),
        2,
    )
    income = round(
        float(
            db.execute(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    Transaction.type == "income",
                    func.substr(Transaction.transaction_time, 1, 10) >= prefix_start,
                    func.substr(Transaction.transaction_time, 1, 10) <= prefix_end,
                )
            ).scalar()
            or 0
        ),
        2,
    )
    expense = round(
        float(
            db.execute(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    Transaction.type == "expense",
                    func.substr(Transaction.transaction_time, 1, 10) >= prefix_start,
                    func.substr(Transaction.transaction_time, 1, 10) <= prefix_end,
                )
            ).scalar()
            or 0
        ),
        2,
    )
    return {
        "start_date": prefix_start,
        "end_date": prefix_end,
        "order_count": int(order_count or 0),
        "order_total_price": total_price,
        "total_income": income,
        "total_expense": expense,
        "net_profit": round(income - expense, 2),
        "avg_order_value": round(total_price / order_count, 2) if order_count else 0,
    }


def service_ranking(db: Session, start_date: str | None = None, end_date: str | None = None, limit: int = 10) -> list[dict]:
    """按服务项目统计件数（依赖结构化订单明细）"""
    from ..models import OrderItem

    stmt = (
        select(
            OrderItem.service_name.label("service_name"),
            func.sum(OrderItem.quantity).label("qty"),
            func.sum(OrderItem.subtotal).label("amount"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .group_by(OrderItem.service_name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(limit)
    )
    if start_date:
        stmt = stmt.where(func.substr(Order.receive_time, 1, 10) >= start_date[:10])
    if end_date:
        stmt = stmt.where(func.substr(Order.receive_time, 1, 10) <= end_date[:10])

    rows = db.execute(stmt).all()
    return [
        {"service_name": r[0] or "", "quantity": int(r[1] or 0), "amount": round(float(r[2] or 0), 2)}
        for r in rows
    ]


def list_transactions(db: Session, limit: int = 100) -> list[dict]:
    rows = db.execute(select(Transaction).order_by(Transaction.id.desc()).limit(limit)).scalars().all()
    return [
        {
            "id": r.id,
            "order_id": r.order_id,
            "type": r.type,
            "amount": float(r.amount or 0),
            "description": r.description or "",
            "transaction_time": r.transaction_time,
        }
        for r in rows
    ]
