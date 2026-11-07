"""管理端 Agent 的工具箱（9 个）

和白名单设计一致：
- 6 个只读：订单列表、订单详情、今日概览、待复核、按手机号查客户、洗护规则
- 3 个写操作：下单、改状态、取衣结算 —— 全部两段式，先返回"待确认动作卡"，
  只有员工在前端点确认（回传 action_id）才真正执行。
工具失败必须返回 ok=False + 可读原因，绝不让模型脑补。
"""
import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Customer, Order, User
from ..services import care_service, catalog_service, order_service, pricing_service, stats_service

# 待确认动作：只放在内存里，10 分钟过期，且按员工账号隔离
ACTION_STORE: dict[str, dict] = {}
ACTION_TTL = 600


def _ok(data):
    return {"ok": True, "data": data}


def _err(message):
    return {"ok": False, "error": message}


def _find_order(db: Session, order_no: str):
    return db.execute(select(Order).where(Order.order_no == (order_no or "").strip())).scalars().first()


def _order_brief(o: dict) -> dict:
    return {
        "order_no": o["order_no"],
        "customer": o["customer_name"],
        "status": o["status"],
        "status_text": o["status_text"],
        "total": o["total_price"],
        "remaining": o["remaining"],
        "items": (o.get("items") or "").replace("\n", "; "),
        "source": o.get("source_text", ""),
    }


# ---------------- 只读 ----------------


def query_orders(ctx, status: str | None = None, keyword: str | None = None, limit: int = 10):
    items = order_service.list_orders(ctx.db, status=status, keyword=keyword, limit=min(int(limit or 10), 20))
    return _ok({"count": len(items), "orders": [_order_brief(o) for o in items]})


def query_order_detail(ctx, order_no: str):
    order = ctx.db.execute(select(Order).where(Order.order_no == (order_no or "").strip())).scalars().first()
    if not order:
        return _err("没有这个订单号")
    data = order_service.to_dict(ctx.db, order)
    return _ok(
        {
            "order_no": data["order_no"],
            "customer": data["customer_name"],
            "phone": data["customer_phone"],
            "status": data["status_text"],
            "source": data["source_text"],
            "review_status": data["review_status_text"],
            "items": [
                {"category": i["category"], "service": i["service_name"], "qty": i["quantity"], "subtotal": i["subtotal"]}
                for i in data["items_detail"]
            ],
            "total": data["total_price"],
            "paid": data["paid_amount"],
            "remaining": data["remaining"],
            "expected_pickup": data["expected_pickup"],
            "amount_logs": data["amount_logs"],
        }
    )


def query_today_overview(ctx):
    return _ok(stats_service.dashboard(ctx.db))


def query_review_pending(ctx):
    rows = order_service.list_review_pending(ctx.db, limit=20)
    return _ok({"count": len(rows), "orders": [_order_brief(o) for o in rows]})


def query_customer(ctx, phone: str):
    """员工按手机号精确查客户：只返回这一位，不做模糊搜索"""
    row = ctx.db.execute(select(Customer).where(Customer.phone == (phone or "").strip())).scalars().first()
    if not row:
        return _err("没有这个手机号对应的客户")
    return _ok(
        {
            "name": row.name,
            "phone": row.phone,
            "level": row.member_level,
            "points": row.points,
            "address": row.address or "",
        }
    )


def query_care_rule(ctx, fabric: str):
    rule = care_service.lookup(ctx.db, fabric)
    if not rule:
        return {"ok": False, "found": False, "error": "规则库里没有这个面料"}
    return {"ok": True, "found": True, "data": rule}


def query_price_list(ctx):
    return _ok({"services": [{"name": s["name"], "price": s["price"]} for s in catalog_service.list_services(ctx.db)]})


# ---------------- 写操作：先给动作卡 ----------------

READ_TOOLS = ("query_orders", "query_order_detail", "query_today_overview", "query_review_pending",
              "query_customer", "query_care_rule", "query_price_list")


def _stage(ctx, tool: str, args: dict, summary: str):
    for key, item in list(ACTION_STORE.items()):
        if time.time() - item["created_at"] > ACTION_TTL:
            ACTION_STORE.pop(key, None)
    action_id = "act_" + uuid.uuid4().hex[:10]
    ACTION_STORE[action_id] = {
        "tool": tool,
        "args": args,
        "summary": summary,
        "staff_id": ctx.user.id,
        "created_at": time.time(),
    }
    return _ok(
        {
            "require_confirm": True,
            "action_id": action_id,
            "summary": summary,
            "note": "这是待确认动作，系统还没有执行；等员工点确认后才会真正写入。",
        }
    )


def propose_create_order(ctx, customer_phone: str, items: str, deposit: float = 0, expected_pickup: str | None = None):
    if not (items or "").strip():
        return _err("需要衣物明细，例如 外套-干洗×2")
    phone = (customer_phone or "").strip()
    if not phone:
        return _err("下单需要客户手机号")
    quote = pricing_service.quote(ctx.db, items_detail=None, items_text=items, customer_phone=phone)
    customer = ctx.db.execute(select(Customer).where(Customer.phone == phone)).scalars().first()
    name = customer.name if customer else ""
    return _stage(
        ctx,
        "create_order",
        {"customer_phone": phone, "customer_name": name, "items": items,
         "deposit": float(deposit or 0), "expected_pickup": expected_pickup},
        f"给 {name or phone}（{phone}）下单：{items}，应收 ¥{quote['total']:.2f}（含会员折扣），预收 ¥{float(deposit or 0):.2f}",
    )


def propose_change_status(ctx, order_no: str, status: str):
    order = ctx.db.execute(select(Order).where(Order.order_no == (order_no or "").strip())).scalars().first()
    if not order:
        return _err("没有这个订单号")
    allowed = ("received", "washing", "ready", "completed", "cancelled")
    if status not in allowed:
        return _err("状态只能是：" + " / ".join(allowed))
    return _stage(
        ctx,
        "change_status",
        {"order_no": order.order_no, "status": status},
        f"把订单 {order.order_no} 从「{order_service.status_text(order.status)}」改成「{order_service.status_text(status)}」",
    )


def propose_complete_order(ctx, order_no: str, pay_amount: float | None = None):
    order = ctx.db.execute(select(Order).where(Order.order_no == (order_no or "").strip())).scalars().first()
    if not order:
        return _err("没有这个订单号")
    remain = round(float(order.total_price or 0) - float(order.deposit or 0), 2)
    amount = float(pay_amount) if pay_amount is not None else remain
    return _stage(
        ctx,
        "complete_order",
        {"order_no": order.order_no, "pay_amount": amount},
        f"订单 {order.order_no} 取衣结算：本次收款 ¥{amount:.2f}（当前待收 ¥{remain:.2f}），售后订单标记已完成",
    )


write_specs = None  # 在 graph 层统一拼 TOOL_SPECS


def run_staff_tool(ctx, name: str, args: dict | None = None):
    args = args or {}
    funcs = {
        "query_orders": query_orders,
        "query_order_detail": query_order_detail,
        "query_today_overview": query_today_overview,
        "query_review_pending": query_review_pending,
        "query_customer": query_customer,
        "query_care_rule": query_care_rule,
        "query_price_list": query_price_list,
        "propose_create_order": propose_create_order,
        "propose_change_status": propose_change_status,
        "propose_complete_order": propose_complete_order,
    }
    fn = funcs.get(name)
    if not fn:
        return _err("不允许调用的工具：" + str(name))
    try:
        return fn(ctx, **args)
    except TypeError as exc:
        return _err("参数不正确：" + str(exc))
    except Exception as exc:  # 业务错误统一转成可读原因，不抛给模型
        return _err(str(exc))


def execute_action(db: Session, user: User, action_id: str) -> dict:
    """员工确认后真正执行写操作"""
    item = ACTION_STORE.get(action_id)
    if not item:
        return _err("这个待确认动作已经过期或不存在，请重新发起")
    if item["staff_id"] != user.id:
        return _err("这个动作不属于当前账号")
    if time.time() - item["created_at"] > ACTION_TTL:
        ACTION_STORE.pop(action_id, None)
        return _err("动作已过期（超过 10 分钟），请重新发起")
    ACTION_STORE.pop(action_id, None)

    tool, args = item["tool"], item["args"]
    if tool == "create_order":
        data = order_service.create_order(
            db,
            customer_name=args.get("customer_name") or "线上客户",
            customer_phone=args["customer_phone"],
            items_detail=None,
            items_text=args["items"],
            deposit=args.get("deposit", 0),
            pay_now=bool(args.get("deposit", 0)),
            expected_pickup=args.get("expected_pickup"),
            staff_id=user.id,
        )
        return _ok({"executed": "create_order", "order_no": data["order_no"], "total": data["total_price"]})
    if tool == "change_status":
        order = _find_order(db, args["order_no"])
        if not order:
            return _err("订单不存在或已被删除")
        data = order_service.change_status(db, order.id, args["status"])
        return _ok({"executed": "change_status", "order_no": args["order_no"], "status": data["status_text"]})
    if tool == "complete_order":
        order = _find_order(db, args["order_no"])
        if not order:
            return _err("订单不存在或已被删除")
        data = order_service.complete_order(db, order.id, staff_id=user.id)
        return _ok(
            {
                "executed": "complete_order",
                "order_no": args["order_no"],
                "settled": data.get("settled_amount", 0),
                "points": data.get("points", {}),
            }
        )
    return _err("未知的待确认动作")
