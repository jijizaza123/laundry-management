"""订单路由"""
from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, require_staff
from ..models import User
from ..schemas import AmountAdjustRequest, OrderCreate, OrderStatusRequest, QuoteRequest
from ..services import log_service, order_service, pricing_service

router = APIRouter(prefix="/api/orders", tags=["订单"], dependencies=[Depends(require_staff)])


@router.get("", summary="订单列表，支持状态与关键词筛选")
def list_orders(
    status: str | None = Query(None, description="received/washing/ready/completed/cancelled"),
    keyword: str | None = Query(None, description="订单号、客户姓名或手机号"),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    return order_service.list_orders(db, status=status, keyword=keyword, limit=limit)


@router.get("/overdue", summary="逾期未取订单")
def overdue(db: Session = Depends(get_db)):
    rows = order_service.overdue_orders(db)
    return {"count": len(rows), "orders": rows}


@router.get("/review-pending", summary="待复核 / 待客户确认金额的线上订单")
def review_pending(limit: int = Query(100, ge=1, le=200), db: Session = Depends(get_db)):
    rows = order_service.list_review_pending(db, limit=limit)
    return {"count": len(rows), "orders": rows}


@router.post("/{order_id}/adjust", summary="到店复核调价（留痕，等客户确认）")
def adjust_amount(
    order_id: int,
    payload: AmountAdjustRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"success": True, "data": order_service.adjust_amount(db, order_id, payload.new_total, payload.reason, user.id)}


@router.post("/{order_id}/approve", summary="到店复核通过（金额不变）")
def approve_amount(
    order_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"success": True, "data": order_service.approve_amount(db, order_id, user.id)}


@router.post("/quote", summary="试算金额（服务端按价目表 + 会员折扣计算）")
def quote(payload: QuoteRequest, db: Session = Depends(get_db)):
    detail = [i.model_dump() for i in payload.items_detail] if payload.items_detail else None
    return pricing_service.quote(
        db, items_detail=detail, items_text=payload.items, customer_phone=payload.customer_phone
    )


@router.get("/{order_id}", summary="订单详情")
def get_order(order_id: int, db: Session = Depends(get_db)):
    return order_service.get_order(db, order_id)


@router.post("", summary="创建订单（收衣），金额由服务端计算")
def create_order(payload: OrderCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    detail = [i.model_dump() for i in payload.items_detail] if payload.items_detail else None
    if not detail and not payload.items:
        return {"error": "请提供 items_detail 或 items", "message": "请提供 items_detail 或 items"}
    data = order_service.create_order(
        db,
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        items_detail=detail,
        items_text=payload.items,
        deposit=payload.deposit,
        pay_now=payload.pay_now,
        expected_pickup=payload.expected_pickup,
        staff_id=user.id,
        declared_total=payload.total_price,
    )
    log_service.add_log(
        db,
        "create_order",
        data["order_no"],
        "创建订单，客户：" + payload.customer_name + "，应收 " + str(data["total_price"]) + " 元",
        user.id,
    )
    return {**data, "message": "订单创建成功"}


@router.put("/{order_id}", summary="修改订单明细或定金")
def update_order(
    order_id: int,
    body: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    status = body.get("status")
    if status:
        # 兼容旧调用：PUT {status: completed}
        if status == "completed":
            data = order_service.complete_order(db, order_id, user.id)
            log_service.add_log(db, "complete_order", str(data["order_no"]), "取衣结算", user.id)
            return {**data, "message": "结算成功"}
        data = order_service.change_status(db, order_id, status)
        log_service.add_log(db, "status_" + status, str(data["order_no"]), "状态变更为" + data["status_text"], user.id)
        return {**data, "message": "状态已更新"}

    detail = body.get("items_detail")
    detail = [i for i in detail] if detail else None
    data = order_service.update_order(
        db,
        order_id,
        items_detail=detail,
        items_text=body.get("items"),
        deposit=body.get("deposit"),
        declared_total=body.get("total_price"),
    )
    log_service.add_log(db, "update_order", str(order_id), "修改订单", user.id)
    return {**data, "message": "修改成功"}


@router.post("/{order_id}/status", summary="状态流转：washing 洗涤中 / ready 可取衣")
def change_status(
    order_id: int,
    payload: OrderStatusRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = order_service.change_status(db, order_id, payload.status)
    log_service.add_log(db, "status_" + payload.status, str(data["order_no"]), "状态变更为" + data["status_text"], user.id)
    return {**data, "message": "状态已更新"}


@router.post("/{order_id}/complete", summary="取衣结算（幂等，重复调用返回 409）")
def complete_order(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    data = order_service.complete_order(db, order_id, user.id)
    log_service.add_log(
        db, "complete_order", str(data["order_no"]), "取衣结算，实收 " + str(data["settled_amount"]), user.id
    )
    return {**data, "message": "结算成功"}


@router.post("/{order_id}/cancel", summary="取消订单")
def cancel_order(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    data = order_service.cancel_order(db, order_id, user.id)
    log_service.add_log(db, "cancel_order", str(data["order_no"]), "取消订单", user.id)
    return {**data, "message": "订单已取消"}


@router.delete("/{order_id}", summary="删除订单（已完成订单禁止删除）")
def delete_order(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    order_service.delete_order(db, order_id)
    log_service.add_log(db, "delete_order", str(order_id), "删除订单", user.id)
    return {"success": True, "message": "删除成功"}
