"""站内消息：调价待确认、衣服可取、预约状态变化

真实项目里这一步走短信/微信模板消息；本地课设用站内消息把"客户怎么知道"
这条链路补完整 —— 客户不刷新页面也能在导航上看到红点。
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Notification, now_str

TYPE_TEXT = {
    "price_adjusted": "金额待确认",
    "ready": "可取衣",
    "appointment": "预约通知",
    "cancelled": "订单取消",
    "info": "通知",
}


def to_dict(n: Notification) -> dict:
    return {
        "id": n.id,
        "type": n.type,
        "type_text": TYPE_TEXT.get(n.type, TYPE_TEXT["info"]),
        "title": n.title or "",
        "body": n.body or "",
        "order_id": n.order_id,
        "is_read": int(n.is_read or 0),
        "created_at": n.created_at,
    }


def notify(
    db: Session,
    customer_id: int | None,
    type: str,
    title: str,
    body: str = "",
    order_id: int | None = None,
) -> Notification | None:
    """写一条消息（不 commit，跟着业务事务一起提交，避免"消息写了业务没成"）"""
    if not customer_id:
        return None
    n = Notification(
        customer_id=int(customer_id),
        type=type,
        title=(title or "")[:100],
        body=(body or "")[:1000],
        order_id=order_id,
        is_read=0,
        created_at=now_str(),
    )
    db.add(n)
    db.flush()
    return n


def list_of_customer(db: Session, customer_id: int, limit: int = 50, only_unread: bool = False) -> list[dict]:
    stmt = select(Notification).where(Notification.customer_id == int(customer_id))
    if only_unread:
        stmt = stmt.where(Notification.is_read == 0)
    stmt = stmt.order_by(Notification.id.desc()).limit(max(1, min(int(limit), 200)))
    return [to_dict(n) for n in db.execute(stmt).scalars().all()]


def unread_count(db: Session, customer_id: int) -> int:
    rows = db.execute(
        select(Notification.id).where(Notification.customer_id == int(customer_id), Notification.is_read == 0)
    ).all()
    return len(rows)


def mark_read(db: Session, customer_id: int, ids: list[int] | None = None) -> int:
    """不传 ids 就是全部已读；返回本次标记条数"""
    stmt = select(Notification).where(Notification.customer_id == int(customer_id), Notification.is_read == 0)
    if ids:
        stmt = stmt.where(Notification.id.in_([int(i) for i in ids]))
    rows = db.execute(stmt).scalars().all()
    for n in rows:
        n.is_read = 1
    db.commit()
    return len(rows)
