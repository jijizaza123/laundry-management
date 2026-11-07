"""订单业务：收衣建单、状态流转、取衣结算（幂等）、取消、删除、逾期查询"""
import random
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import (
    ACTIVE_STATUSES,
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_COMPLETED,
    ORDER_STATUS_READY,
    ORDER_STATUS_RECEIVED,
    ORDER_STATUS_TEXT,
    ORDER_STATUS_WASHING,
    STATUS_TRANSITIONS,
)
from ..exceptions import ConflictError, NotFoundError, ServiceError
from ..models import Order, OrderAmountLog, OrderItem, Transaction, now_str

REVIEW_STATUS_TEXT = {
    "confirmed": "金额已确认",
    "pending": "待到店复核",
    "adjusted": "门店调价，待你确认",
}
SOURCE_TEXT = {"staff": "到店", "online": "客户端下单"}
from . import customer_service, inventory_service, notification_service, pricing_service
from .items_parser import parse_items_text  # noqa: F401  （对外保留导出，兼容旧调用）

VALID_STATUSES = (ORDER_STATUS_RECEIVED, ORDER_STATUS_WASHING, ORDER_STATUS_READY, ORDER_STATUS_COMPLETED, ORDER_STATUS_CANCELLED)


def generate_order_no(db: Session) -> str:
    """毫秒级时间戳 + 4 位随机，避免同秒冲突"""
    for _ in range(20):
        candidate = "O" + datetime.now().strftime("%Y%m%d%H%M%S%f")[:-3] + str(random.randint(0, 9999)).zfill(4)
        exists = db.execute(select(Order.id).where(Order.order_no == candidate)).first()
        if not exists:
            return candidate
    raise ConflictError("订单号生成失败，请重试")


def paid_amount(db: Session, order_id: int) -> float:
    rows = (
        db.execute(
            select(Transaction).where(Transaction.order_id == order_id, Transaction.type == "income")
        )
        .scalars()
        .all()
    )
    return round(sum(t.amount or 0 for t in rows), 2)


def status_text(status: str) -> str:
    return ORDER_STATUS_TEXT.get(status, status)


def to_dict(db: Session, order: Order) -> dict:
    customer = order.customer
    paid = paid_amount(db, order.id)
    total = float(order.total_price or 0)
    original = float(order.original_amount or 0) or total
    overdue = False
    if order.expected_pickup and order.status in ACTIVE_STATUSES:
        overdue = order.expected_pickup[:10] < datetime.now().strftime("%Y-%m-%d")
    return {
        "id": order.id,
        "order_no": order.order_no,
        "customer_id": order.customer_id,
        "customer_name": customer.name if customer else "",
        "customer_phone": customer.phone if customer else "",
        "member_level": customer.member_level if customer else 0,
        "items": order.items or "",
        "original_amount": round(original, 2),
        "discount_rate": float(order.discount_rate or 1.0),
        "discount_amount": round(original - total, 2),
        "total_price": total,
        "deposit": float(order.deposit or 0),
        "paid_amount": paid,
        "remaining": round(max(total - paid, 0), 2),
        "status": order.status,
        "status_text": status_text(order.status),
        "receive_time": order.receive_time,
        "expected_pickup": order.expected_pickup,
        "actual_pickup": order.actual_pickup,
        "overdue": overdue,
        "items_detail": [
            {
                "category": i.category,
                "service_name": i.service_name,
                "unit_price": i.unit_price,
                "quantity": i.quantity,
                "subtotal": i.subtotal,
            }
            for i in order.item_rows
        ],
        "item_count": sum(i.quantity for i in order.item_rows),
        "source": order.source or "staff",
        "source_text": SOURCE_TEXT.get(order.source or "staff", "到店"),
        "appointment_id": order.appointment_id,
        "review_status": order.review_status or "confirmed",
        "review_status_text": REVIEW_STATUS_TEXT.get(order.review_status or "confirmed", ""),
        "amount_logs": _unconfirmed_logs(db, order.id),
    }


def _yuan(value) -> str:
    """消息文案里的金额统一两位小数，避免出现 105.0 元这种半成品"""
    return f"{float(value or 0):.2f}"


def _unconfirmed_logs(db: Session, order_id: int) -> list[dict]:
    rows = (
        db.execute(
            select(OrderAmountLog)
            .where(OrderAmountLog.order_id == order_id, OrderAmountLog.customer_confirmed == 0)
            .order_by(OrderAmountLog.id.desc())
        )
        .scalars()
        .all()
    )
    return [
        {"old_total": round(float(r.old_total or 0), 2), "new_total": round(float(r.new_total or 0), 2),
         "reason": r.reason or "", "created_at": r.created_at}
        for r in rows
    ]


def _require_order(db: Session, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if not order or (order.is_deleted or 0):
        raise NotFoundError("订单不存在")
    return order


def _replace_items(db: Session, order: Order, lines: list[dict]) -> None:
    order.item_rows.clear()
    db.flush()
    for line in lines:
        db.add(
            OrderItem(
                order_id=order.id,
                category=line["category"],
                service_name=line["service_name"],
                unit_price=line["unit_price"],
                quantity=line["quantity"],
                subtotal=line["subtotal"],
            )
        )


def create_order(
    db: Session,
    customer_name: str,
    customer_phone: str,
    items_detail: list[dict] | None = None,
    items_text: str | None = None,
    deposit: float = 0,
    pay_now: bool = False,
    expected_pickup: str | None = None,
    staff_id: int = 1,
    declared_total: float | None = None,
) -> dict:
    """建单。金额由服务端按价目表 + 会员折扣计算，declared_total 只用于校验一致性"""
    if not (customer_name or "").strip():
        raise ServiceError("客户姓名不能为空")
    if not (customer_phone or "").strip():
        raise ServiceError("客户手机号不能为空")

    customer = customer_service.get_or_create_by_phone(db, customer_name, customer_phone)

    quote = pricing_service.quote(db, items_detail=items_detail, items_text=items_text, customer_phone=customer_phone)
    total = quote["total"]
    dep = round(float(deposit or 0), 2)
    if dep < 0:
        raise ServiceError("定金不能为负")
    if dep > total:
        raise ServiceError("定金不能大于应收金额 " + str(total))
    if declared_total is not None and abs(round(float(declared_total), 2) - total) >= 0.01:
        raise ServiceError("提交金额与明细计算结果不一致，应收 " + str(total) + " 元，请刷新后重试")

    order = Order(
        order_no=generate_order_no(db),
        customer_id=customer.id,
        items=quote["items_text"],
        original_amount=quote["subtotal"],
        discount_rate=quote["discount_rate"],
        member_level_snapshot=quote["member_level"],
        total_price=total,
        deposit=dep,
        status=ORDER_STATUS_RECEIVED,
        receive_time=now_str(),
        expected_pickup=expected_pickup,
        staff_id=staff_id,
    )
    db.add(order)
    db.flush()
    _replace_items(db, order, quote["lines"])

    if pay_now and dep > 0:
        db.add(
            Transaction(
                order_id=order.id,
                type="income",
                amount=dep,
                description="收衣时支付定金",
                staff_id=staff_id,
                transaction_time=now_str(),
            )
        )

    db.commit()
    db.refresh(order)
    data = to_dict(db, order)
    data["quote"] = quote
    return data


def list_orders(
    db: Session,
    status: str | None = None,
    keyword: str | None = None,
    limit: int = 200,
) -> list[dict]:
    stmt = select(Order).where(Order.is_deleted == 0)
    if keyword:
        kw = "%" + keyword.strip() + "%"
        from ..models import Customer

        stmt = stmt.join(Customer, Order.customer_id == Customer.id, isouter=True).where(
            (Order.order_no.like(kw)) | (Customer.name.like(kw)) | (Customer.phone.like(kw))
        )
    if status:
        if status not in VALID_STATUSES:
            raise ServiceError("未知的订单状态：" + status)
        stmt = stmt.where(Order.status == status)
    stmt = stmt.order_by(Order.id.desc()).limit(limit)
    return [to_dict(db, o) for o in db.execute(stmt).scalars().all()]


def get_order(db: Session, order_id: int) -> dict:
    return to_dict(db, _require_order(db, order_id))


def update_order(
    db: Session,
    order_id: int,
    items_detail: list[dict] | None = None,
    items_text: str | None = None,
    deposit: float | None = None,
    declared_total: float | None = None,
) -> dict:
    """修改明细或定金。改明细会重新按价目表与会员折扣计价"""
    order = _require_order(db, order_id)
    if order.status in (ORDER_STATUS_COMPLETED, ORDER_STATUS_CANCELLED):
        raise ConflictError("订单已" + status_text(order.status) + "，不能再修改明细或金额")

    if items_detail or items_text:
        phone = order.customer.phone if order.customer else None
        quote = pricing_service.quote(
            db, items_detail=items_detail, items_text=items_text, customer_phone=phone
        )
        if declared_total is not None and abs(round(float(declared_total), 2) - quote["total"]) >= 0.01:
            raise ServiceError("提交金额与明细计算结果不一致，应收 " + str(quote["total"]) + " 元")
        order.items = quote["items_text"]
        order.original_amount = quote["subtotal"]
        order.discount_rate = quote["discount_rate"]
        order.total_price = quote["total"]
        _replace_items(db, order, quote["lines"])

    if deposit is not None:
        dep = round(float(deposit), 2)
        if dep < 0:
            raise ServiceError("定金不能为负")
        if dep > float(order.total_price or 0):
            raise ServiceError("定金不能大于应收金额")
        order.deposit = dep

    db.commit()
    db.refresh(order)
    return to_dict(db, order)


def change_status(db: Session, order_id: int, target_status: str) -> dict:
    """状态流转：received -> washing -> ready -> completed"""
    if target_status not in VALID_STATUSES:
        raise ServiceError("未知的订单状态：" + target_status)
    order = _require_order(db, order_id)
    allowed = STATUS_TRANSITIONS.get(target_status, ())
    if order.status not in allowed:
        raise ConflictError(
            "订单当前状态为「" + status_text(order.status) + "」，不能变更为「" + status_text(target_status) + "」"
        )
    order.status = target_status
    if target_status == ORDER_STATUS_READY and order.customer_id:
        notification_service.notify(
            db,
            order.customer_id,
            "ready",
            "衣服洗好了，可以取衣：" + order.order_no,
            "共 " + str(sum(int(i.quantity or 0) for i in order.item_rows)) + " 件已可取，"
            "待付 " + _yuan(max(float(order.total_price or 0) - paid_amount(db, order.id), 0)) + " 元。",
            order.id,
        )
    db.commit()
    db.refresh(order)
    return to_dict(db, order)


def complete_order(db: Session, order_id: int, staff_id: int = 1) -> dict:
    """取衣结算：幂等保护 + 按实收金额补差 + 累计积分"""
    order = _require_order(db, order_id)
    if order.status == ORDER_STATUS_COMPLETED:
        raise ConflictError("订单已完成结算，请勿重复操作")
    if order.status == ORDER_STATUS_CANCELLED:
        raise ConflictError("订单已取消，不能结算")
    # P0-1：线上单的金额必须先落定，否则"客户确认"只是界面上的安慰
    #   pending  = 门店还没复核，金额可能是错的
    #   adjusted = 门店改了价，客户还没点确认
    review = order.review_status or "confirmed"
    if review in ("pending", "adjusted"):
        raise ConflictError(
            "该订单" + REVIEW_STATUS_TEXT.get(review, review) + "，不能结算。"
            "请先到「到店复核」完成金额确认" + ("，或等客户在客户端点「确认新金额」" if review == "adjusted" else "")
        )

    total = round(float(order.total_price or 0), 2)
    paid = paid_amount(db, order.id)
    remaining = round(total - paid, 2)

    if remaining > 0:
        db.add(
            Transaction(
                order_id=order.id,
                type="income",
                amount=remaining,
                description="取衣结算",
                staff_id=staff_id,
                transaction_time=now_str(),
            )
        )

    order.status = ORDER_STATUS_COMPLETED
    order.actual_pickup = now_str()
    db.commit()

    points_info = {"points_gained": 0, "points": 0, "member_level": 0}
    customer = customer_service.get_by_phone(db, order.customer.phone) if order.customer else None
    if customer:
        points_info = customer_service.add_points_for_amount(db, customer, total)

    # 库存与订单挂钩：按件扣耗材并留用量流水（P1）
    usage = inventory_service.consume_for_order(db, order)
    db.commit()

    db.refresh(order)
    data = to_dict(db, order)
    data["settled_amount"] = round(max(remaining, 0), 2)
    data["points"] = points_info
    data["inventory"] = usage
    return data


def cancel_order(db: Session, order_id: int, staff_id: int = 1) -> dict:
    order = _require_order(db, order_id)
    if order.status == ORDER_STATUS_COMPLETED:
        raise ConflictError("订单已完成，不能取消")
    if order.status == ORDER_STATUS_CANCELLED:
        raise ConflictError("订单已取消，请勿重复操作")
    # P0-5：取消要留下退款痕迹，不能只改一个状态
    refund = paid_amount(db, order.id)
    if refund > 0:
        db.add(
            Transaction(
                order_id=order.id,
                type="refund",
                amount=-round(refund, 2),
                description="取消订单退款（红冲）",
                staff_id=staff_id,
                transaction_time=now_str(),
            )
        )
    order.status = ORDER_STATUS_CANCELLED
    if order.customer_id:
        notification_service.notify(
            db,
            order.customer_id,
            "cancelled",
            "订单已取消：" + order.order_no,
            "订单已取消" + (("，已退 " + _yuan(refund) + " 元") if refund > 0 else "") + "。",
            order.id,
        )
    db.commit()
    db.refresh(order)
    data = to_dict(db, order)
    data["refunded"] = round(refund, 2)
    return data


def overdue_orders(db: Session, only_active: bool = True) -> list[dict]:
    """逾期未取：预计取衣日期早于今天且仍在店内"""
    today = datetime.now().strftime("%Y-%m-%d")
    stmt = select(Order).where(Order.expected_pickup.is_not(None)).where(Order.expected_pickup != "")
    stmt = stmt.where(Order.is_deleted == 0)
    stmt = stmt.where(Order.status.in_(ACTIVE_STATUSES) if only_active else Order.status != ORDER_STATUS_CANCELLED)
    rows = [o for o in db.execute(stmt).scalars().all() if (o.expected_pickup or "")[:10] < today]
    rows.sort(key=lambda o: o.expected_pickup or "")
    return [to_dict(db, o) for o in rows]


def delete_order(db: Session, order_id: int) -> None:
    """软删除：行还在、流水还在，只是从所有列表里消失（P0-5：财务必须可审计）"""
    order = _require_order(db, order_id)
    if order.status == ORDER_STATUS_COMPLETED:
        raise ConflictError("已完成的订单涉及财务流水，不允许删除，请改用取消或作废流程")
    order.is_deleted = 1
    order.status = ORDER_STATUS_CANCELLED
    db.commit()


# ---------------- 客户端视角（严格按 customer_id 过滤） ----------------


def list_orders_of_customer(
    db: Session,
    customer_id: int,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """只返回该客户本人订单。customer_id 由登录态注入，不接受外部传入"""
    stmt = select(Order).where(Order.customer_id == int(customer_id), Order.is_deleted == 0)
    if status:
        if status not in VALID_STATUSES:
            raise ServiceError("未知的订单状态：" + status)
        stmt = stmt.where(Order.status == status)
    stmt = stmt.order_by(Order.id.desc()).limit(max(1, min(int(limit or 50), 100)))
    return [to_dict(db, o) for o in db.execute(stmt).scalars().all()]


def get_order_of_customer(db: Session, customer_id: int, order_id: int) -> dict:
    """查本人某一单。不是本人的单统一按"不存在"处理，避免泄露订单是否存在"""
    order = db.get(Order, order_id)
    if not order or order.customer_id != int(customer_id) or (order.is_deleted or 0):
        raise NotFoundError("订单不存在")
    return to_dict(db, order)


def customer_summary(db: Session, customer_id: int) -> dict:
    """客户首页摘要：在店单数、可取衣、待付款、累计消费"""
    orders = (
        db.execute(select(Order).where(Order.customer_id == int(customer_id), Order.is_deleted == 0))
        .scalars()
        .all()
    )
    counts = {key: 0 for key in VALID_STATUSES}
    unpaid = 0.0
    spent = 0.0
    for order in orders:
        counts[order.status] = counts.get(order.status, 0) + 1
        paid = paid_amount(db, order.id)
        spent += paid
        if order.status in ACTIVE_STATUSES:
            unpaid += max(float(order.total_price or 0) - paid, 0)

    latest = None
    if orders:
        newest = max(orders, key=lambda o: o.id)
        latest = to_dict(db, newest)

    return {
        "customer_id": int(customer_id),
        "total_orders": len(orders),
        "counts": counts,
        "active_count": sum(counts[s] for s in ACTIVE_STATUSES),
        "ready_count": counts.get(ORDER_STATUS_READY, 0),
        "unpaid_amount": round(unpaid, 2),
        "total_spent": round(spent, 2),
        "latest_order": latest,
    }


# ---------------- 三期：客户端线上下单 + 到店复核 ----------------


def create_online_order(
    db: Session,
    customer,
    items_detail: list[dict] | None = None,
    items_text: str | None = None,
    expected_pickup: str | None = None,
    appointment_id: int | None = None,
) -> dict:
    """客户自己下单。金额仍由服务端按价目表 + 会员折扣算，客户改不了价。

    生成的单 review_status=pending：门店取件时要按实际件数/面料复核，
    如果金额有变，走 adjust_amount 留痕，客户确认后才生效。
    """
    if not items_detail and not (items_text or "").strip():
        raise ServiceError("请至少选一件衣物")

    quote = pricing_service.quote(
        db, items_detail=items_detail, items_text=items_text, customer_phone=customer.phone
    )

    if appointment_id:
        from ..models import Appointment

        appt = db.get(Appointment, int(appointment_id))
        if not appt or appt.customer_id != customer.id:
            raise NotFoundError("预约不存在")
        if appt.status not in ("pending", "confirmed"):
            raise ConflictError("该预约已结束，不能再关联新订单")

    order = Order(
        order_no=generate_order_no(db),
        customer_id=customer.id,
        items=quote["items_text"],
        original_amount=quote["subtotal"],
        discount_rate=quote["discount_rate"],
        member_level_snapshot=quote["member_level"],
        total_price=quote["total"],
        deposit=0,
        status=ORDER_STATUS_RECEIVED,
        receive_time=now_str(),
        expected_pickup=expected_pickup,
        staff_id=None,
        source="online",
        appointment_id=int(appointment_id) if appointment_id else None,
        review_status="pending",
    )
    db.add(order)
    db.flush()
    _replace_items(db, order, quote["lines"])
    db.commit()
    db.refresh(order)
    data = to_dict(db, order)
    data["quote"] = quote
    return data


def list_review_pending(db: Session, limit: int = 100) -> list[dict]:
    """待复核 / 已调价待确认的单，给门店工作台用"""
    stmt = (
        select(Order)
        .where(Order.review_status.in_(("pending", "adjusted")))
        .where(Order.status != ORDER_STATUS_CANCELLED)
        .where(Order.is_deleted == 0)
        .order_by(Order.id.desc())
        .limit(max(1, min(int(limit or 100), 200)))
    )
    return [to_dict(db, o) for o in db.execute(stmt).scalars().all()]


def adjust_amount(db: Session, order_id: int, new_total: float, reason: str, staff_id: int | None = None) -> dict:
    """门店复核后调价：金额变化必须留痕，等客户确认"""
    order = _require_order(db, order_id)
    if order.status in (ORDER_STATUS_COMPLETED, ORDER_STATUS_CANCELLED):
        raise ConflictError("订单已" + status_text(order.status) + "，不能再调价")
    if (order.review_status or "confirmed") not in ("pending", "adjusted"):
        raise ConflictError("这单不是线上订单，没有复核流程；要改金额请走修改明细")

    total = round(float(new_total or 0), 2)
    if total <= 0:
        raise ServiceError("新的应收金额必须大于 0")
    old_total = round(float(order.total_price or 0), 2)
    if abs(total - old_total) < 0.01:
        raise ServiceError("金额没有变化，不需要调价")

    note = (reason or "").strip()
    if not note:
        raise ServiceError("调价必须写明原因，比如「实际 3 件，客户下单填 2 件」")
    if len(note) > 300:
        raise ServiceError("原因太长了，请精简到 300 字以内")

    db.add(
        OrderAmountLog(
            order_id=order.id,
            old_total=old_total,
            new_total=total,
            reason=note,
            staff_id=staff_id,
            customer_confirmed=0,
        )
    )
    order.total_price = total
    order.review_status = "adjusted"
    if order.customer_id:
        notification_service.notify(
            db,
            order.customer_id,
            "price_adjusted",
            "订单金额有调整，待你确认：" + order.order_no,
            "从 " + _yuan(old_total) + " 元调整为 " + _yuan(total) + " 元（" + note + "），请在「我的订单」里确认。",
            order.id,
        )
    db.commit()
    db.refresh(order)
    return to_dict(db, order)


def approve_amount(db: Session, order_id: int, staff_id: int | None = None) -> dict:
    """复核后金额与客户下单一致：直接通过，不留调价记录"""
    order = _require_order(db, order_id)
    if order.status in (ORDER_STATUS_COMPLETED, ORDER_STATUS_CANCELLED):
        raise ConflictError("订单已" + status_text(order.status) + "，不能复核")
    if (order.review_status or "confirmed") != "pending":
        raise ConflictError("这单不在待复核状态")
    order.review_status = "confirmed"
    if staff_id:
        order.staff_id = staff_id
    db.commit()
    db.refresh(order)
    return to_dict(db, order)


def confirm_amount(db: Session, customer_id: int, order_id: int) -> dict:
    """客户确认门店调价后的金额。只有本人、且确实有待确认的调价才能操作"""
    order = db.get(Order, order_id)
    if not order or order.customer_id != int(customer_id):
        raise NotFoundError("订单不存在")
    if (order.review_status or "confirmed") != "adjusted":
        raise ConflictError("这单没有待你确认的调价")

    for log in (
        db.execute(
            select(OrderAmountLog).where(
                OrderAmountLog.order_id == order.id, OrderAmountLog.customer_confirmed == 0
            )
        )
        .scalars()
        .all()
    ):
        log.customer_confirmed = 1
    order.review_status = "confirmed"
    db.commit()
    db.refresh(order)
    return to_dict(db, order)


