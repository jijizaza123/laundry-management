"""客户端接口（/api/my/*）

安全约定：
- 所有接口的客户身份都来自 token 里的 customer_id，签名里不出现手机号/客户 ID 参数
- 任何跨客户访问都返回"不存在"，不返回"禁止访问 + 对方信息"
"""
from fastapi import APIRouter, Depends, Query
import time
from sqlalchemy.orm import Session

from ..agent import run_chat
from ..config import LEVEL_NAMES, LEVEL_THRESHOLDS, MEMBER_DISCOUNT
from ..db import get_db
from ..deps import require_customer
from ..models import Customer
from ..schemas import AppointmentCreateRequest, ChatRequest, OnlineOrderRequest
from ..services import (
    appointment_service,
    care_service,
    catalog_service,
    chat_service,
    metric_service,
    notification_service,
    order_service,
    pricing_service,
)

router = APIRouter(prefix="/api/my", tags=["客户自助"], dependencies=[Depends(require_customer)])


def _next_level(points: int) -> dict:
    """距离下一等级还差多少积分"""
    current = 0
    for threshold, level in LEVEL_THRESHOLDS:
        if points >= threshold:
            current = level
            break
    higher = sorted([(t, l) for t, l in LEVEL_THRESHOLDS if l > current])
    if not higher:
        return {"level": None, "level_name": None, "need_points": 0, "at_top": True}
    threshold, level = higher[0]
    return {
        "level": level,
        "level_name": LEVEL_NAMES.get(level, ""),
        "need_points": int(threshold - points),
        "at_top": False,
    }


def _profile_payload(customer: Customer) -> dict:
    points = int(customer.points or 0)
    level = int(customer.member_level or 0)
    return {
        "customer_id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
        "address": customer.address or "",
        "member_level": level,
        "level_name": LEVEL_NAMES.get(level, "普通客户"),
        "points": points,
        "discount": MEMBER_DISCOUNT.get(level, 1.0),
        "next_level": _next_level(points),
    }


@router.get("/profile", summary="我的资料：等级、积分、折扣")
def my_profile(customer: Customer = Depends(require_customer)):
    return {"success": True, "data": _profile_payload(customer)}


@router.get("/summary", summary="我的概览：在店/可取衣/待付款/累计消费")
def my_summary(
    customer: Customer = Depends(require_customer),
    db: Session = Depends(get_db),
):
    data = order_service.customer_summary(db, customer.id)
    data["profile"] = _profile_payload(customer)
    return {"success": True, "data": data}


@router.get("/orders", summary="我的订单列表")
def my_orders(
    status: str | None = None,
    limit: int = 20,
    customer: Customer = Depends(require_customer),
    db: Session = Depends(get_db),
):
    rows = order_service.list_orders_of_customer(db, customer.id, status=status, limit=limit)
    return {"success": True, "data": rows}


@router.get("/orders/{order_id}", summary="我的某一单详情")
def my_order_detail(
    order_id: int,
    customer: Customer = Depends(require_customer),
    db: Session = Depends(get_db),
):
    return {"success": True, "data": order_service.get_order_of_customer(db, customer.id, order_id)}


@router.get("/options", summary="下单用的选项：分类、服务价目、我能查的洗护面料")
def my_options(
    customer: Customer = Depends(require_customer),
    db: Session = Depends(get_db),
):
    return {
        "success": True,
        "data": {
            "categories": [c["name"] for c in catalog_service.list_categories(db)],
            "services": [{"name": s["name"], "price": s["price"], "unit": s["unit"]} for s in catalog_service.list_services(db)],
            "fabrics": [r["fabric"] for r in care_service.list_rules(db)],
            "discount": MEMBER_DISCOUNT.get(int(customer.member_level or 0), 1.0),
        },
    }


@router.post("/quote", summary="下单前试算（服务端计价，含会员折扣）")
def my_quote(
    payload: OnlineOrderRequest,
    customer: Customer = Depends(require_customer),
    db: Session = Depends(get_db),
):
    items_detail = [i.model_dump() for i in payload.items_detail] if payload.items_detail else None
    return {
        "success": True,
        "data": pricing_service.quote(
            db, items_detail=items_detail, items_text=payload.items, customer_phone=customer.phone
        ),
    }


@router.post("/orders", summary="客户端下单（线上下单，待到店复核）")
def create_my_order(
    payload: OnlineOrderRequest,
    customer: Customer = Depends(require_customer),
    db: Session = Depends(get_db),
):
    """金额由服务端算，客户改不了价；生成的单 review_status=pending，门店复核后才最终确定"""
    items_detail = [i.model_dump() for i in payload.items_detail] if payload.items_detail else None
    data = order_service.create_online_order(
        db,
        customer=customer,
        items_detail=items_detail,
        items_text=payload.items,
        expected_pickup=payload.expected_pickup,
        appointment_id=payload.appointment_id,
    )
    return {"success": True, "data": data}


@router.post("/orders/{order_id}/confirm-amount", summary="确认门店复核后的金额")
def confirm_my_amount(
    order_id: int,
    customer: Customer = Depends(require_customer),
    db: Session = Depends(get_db),
):
    return {"success": True, "data": order_service.confirm_amount(db, customer.id, order_id)}


@router.post("/appointments", summary="预约上门取件")
def create_my_appointment(
    payload: AppointmentCreateRequest,
    customer: Customer = Depends(require_customer),
    db: Session = Depends(get_db),
):
    return {
        "success": True,
        "data": appointment_service.create(db, customer, payload.expected_time, payload.address, payload.note or ""),
    }


@router.get("/appointments", summary="我的上门取件预约")
def my_appointments(
    customer: Customer = Depends(require_customer),
    db: Session = Depends(get_db),
):
    return {"success": True, "data": appointment_service.list_of_customer(db, customer.id)}


@router.post("/chat", summary="和我的洗衣助手对话（只读工具）")
def my_chat(
    payload: ChatRequest,
    customer: Customer = Depends(require_customer),
    db: Session = Depends(get_db),
):
    """把模型、工具、会话拼在一起的一次调用。

    安全边界在工具签名里：这里的 customer 来自 token，模型拿不到也改不了。
    """
    key = chat_service.session_key_customer(customer.id)
    history = [m.model_dump() for m in payload.history][-12:]
    if not history:
        history = [{"role": h["role"], "content": h["content"]} for h in chat_service.history(db, key)]

    started = time.perf_counter()
    result = run_chat(db=db, customer=customer, message=payload.message, history=history)
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    chat_service.append(db, key, "user", payload.message)
    chat_service.append(db, key, "assistant", result["answer"], result["tools_used"])
    metric_service.record(
        db,
        session_key=key,
        side="customer",
        question=payload.message,
        answer=result["answer"],
        rounds=result["rounds"],
        tools_used=result["tools_used"],
        elapsed_ms=elapsed_ms,
        ok=not bool(result.get("error")),
    )

    return {
        "success": True,
        "data": {
            "answer": result["answer"],
            "tools_used": result["tools_used"],
            "rounds": result["rounds"],
            "trace": result["trace"],
            "error": bool(result.get("error")),
        },
    }


@router.get("/chat/history", summary="我的对话历史")
def my_chat_history(
    customer: Customer = Depends(require_customer),
    db: Session = Depends(get_db),
):
    key = chat_service.session_key_customer(customer.id)
    return {"success": True, "data": chat_service.history(db, key, limit=30)}


@router.delete("/chat/history", summary="清空我的对话历史")
def clear_my_chat(
    customer: Customer = Depends(require_customer),
    db: Session = Depends(get_db),
):
    chat_service.clear(db, chat_service.session_key_customer(customer.id))
    return {"success": True, "data": {"cleared": True}}


@router.get("/notifications", summary="我的站内消息（含未读数）")
def my_notifications(
    limit: int = Query(30, ge=1, le=100),
    unread_only: bool = Query(False),
    customer: Customer = Depends(require_customer),
    db: Session = Depends(get_db),
):
    rows = notification_service.list_of_customer(db, customer.id, limit=limit, only_unread=unread_only)
    return {
        "success": True,
        "data": rows,
        "unread": notification_service.unread_count(db, customer.id),
    }


@router.post("/notifications/read", summary="把我的消息标为已读（不传 ids 就是全部）")
def read_my_notifications(
    payload: dict | None = None,
    customer: Customer = Depends(require_customer),
    db: Session = Depends(get_db),
):
    ids = (payload or {}).get("ids")
    marked = notification_service.mark_read(db, customer.id, ids)
    return {
        "success": True,
        "data": {"marked": marked, "unread": notification_service.unread_count(db, customer.id)},
    }
