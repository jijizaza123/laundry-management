"""客户端 Agent 的工具层（全部只读）

安全设计：每个工具签名里都没有手机号 / customer_id 参数，
身份由 ToolContext 从登录态注入。模型无论被怎么诱导，
都没有"查别人数据"这个能力可用。
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..config import CARE_FALLBACK_TEXT, LEVEL_NAMES, LEVEL_THRESHOLDS, MEMBER_DISCOUNT
from ..models import Customer
from ..services import care_service, customer_service, order_service
from ..services import catalog_service
from ..services import appointment_service

# OpenAI tools 规范：给模型看的说明书
TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "query_my_orders",
            "description": "查询当前登录客户本人的洗衣订单列表（含状态、金额、预计取衣时间）。不需要任何参数，后端按登录身份过滤。",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["received", "washing", "ready", "completed", "cancelled"],
                        "description": "只看某个状态时传入：received 待洗涤 / washing 洗涤中 / ready 可取衣 / completed 已完成 / cancelled 已取消",
                    },
                    "limit": {"type": "integer", "description": "返回条数，默认 5，最多 10"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_my_order_detail",
            "description": "查询本人某一单的明细：衣物分类、服务项目、单价、件数、小计、折扣、已付和待付。只能查本人的单。",
            "parameters": {
                "type": "object",
                "properties": {"order_no": {"type": "string", "description": "订单号，如 O202611072007577254100"}},
                "required": ["order_no"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_my_account",
            "description": "查询本人的会员信息：等级、折扣、积分、距下一等级还差多少积分、累计消费、未付款金额。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_care_rule",
            "description": "查询某种面料/品类的洗护规则，返回能否水洗、建议工艺、禁忌、原因和依据出处。查不到依据时必须如实说查不到。",
            "parameters": {
                "type": "object",
                "properties": {"fabric": {"type": "string", "description": "面料或品类，如 羊绒、真丝、羽绒服、牛仔裤"}},
                "required": ["fabric"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_price_list",
            "description": "查询门店服务价目表：每个服务项目的单价（元/件）。回答价格问题时必须用它，不要凭印象报数。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_my_appointments",
            "description": "查询当前登录客户本人提交的上门取件预约记录：预约单号、上门时间、状态（待上门/已上门/已取消）。没有参数，后端按登录身份过滤。",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "description": "返回条数，默认 5，最多 10"}},
                "required": [],
            },
        },
    },
]

ALLOWED_TOOLS = {spec["function"]["name"] for spec in TOOL_SPECS}


@dataclass
class ToolContext:
    """工具执行上下文：身份只来自登录态，绝不来自模型参数"""

    db: Session
    customer: Customer


def _brief(order: dict) -> dict:
    """给模型看的精简视图：只保留回答需要的信息，不返回客户手机号等无关字段"""
    return {
        "order_no": order["order_no"],
        "status": order["status_text"],
        "items": order["items"],
        "item_count": order["item_count"],
        "total_price": order["total_price"],
        "paid_amount": order["paid_amount"],
        "remaining": order["remaining"],
        "receive_time": order["receive_time"],
        "expected_pickup": order["expected_pickup"] or "未预约",
        "overdue": order["overdue"],
    }


def query_my_orders(ctx: ToolContext, status: str | None = None, limit: int = 5) -> dict:
    limit = max(1, min(int(limit or 5), 10))
    rows = order_service.list_orders_of_customer(ctx.db, ctx.customer.id, status=status, limit=limit)
    return {"total_returned": len(rows), "orders": [_brief(o) for o in rows]}


def query_my_order_detail(ctx: ToolContext, order_no: str) -> dict:
    order_no = (order_no or "").strip()
    if not order_no:
        return {"found": False, "message": "请提供订单号"}
    rows = order_service.list_orders_of_customer(ctx.db, ctx.customer.id, limit=100)
    for order in rows:
        if order["order_no"] == order_no:
            return {
                "found": True,
                "order_no": order["order_no"],
                "status": order["status_text"],
                "items_detail": order["items_detail"],
                "original_amount": order["original_amount"],
                "discount_rate": order["discount_rate"],
                "discount_amount": order["discount_amount"],
                "total_price": order["total_price"],
                "paid_amount": order["paid_amount"],
                "remaining": order["remaining"],
                "receive_time": order["receive_time"],
                "expected_pickup": order["expected_pickup"] or "未预约",
            }
    # 不属于本人 与 不存在 返回同一句话，避免被用来探测订单是否存在
    return {"found": False, "message": "没有找到这个订单号，请核对后再说一次"}


def query_my_account(ctx: ToolContext) -> dict:
    c = ctx.customer
    summary = order_service.customer_summary(ctx.db, c.id)
    level = int(c.member_level or 0)
    next_level = None
    thresholds = sorted([(t, l) for t, l in LEVEL_THRESHOLDS if l > level])
    if thresholds:
        threshold, lv = thresholds[0]
        next_level = {"level_name": LEVEL_NAMES.get(lv, ""), "need_points": int(threshold - (c.points or 0))}
    return {
        "name": c.name,
        "member_level": level,
        "level_name": customer_service.level_name(level),
        "discount": MEMBER_DISCOUNT.get(level, 1.0),
        "points": int(c.points or 0),
        "next_level": next_level,
        "unpaid_amount": summary["unpaid_amount"],
        "total_spent": summary["total_spent"],
        "active_count": summary["active_count"],
        "ready_count": summary["ready_count"],
    }


def query_care_rule(ctx: ToolContext, fabric: str) -> dict:
    rule = care_service.lookup(ctx.db, fabric)
    if not rule:
        return {
            "found": False,
            "message": CARE_FALLBACK_TEXT,
            "hint": "门店现有洗护规则覆盖：羊绒、羊毛、真丝、羽绒、棉、化纤、皮革、蕾丝、牛仔、西装",
        }
    return {"found": True, **rule}


def query_price_list(ctx: ToolContext) -> dict:
    items = catalog_service.list_services(ctx.db)
    return {
        "unit": "元/件",
        "items": [{"name": i["name"], "price": i["price"], "unit": i["unit"]} for i in items],
    }


def query_my_appointments(ctx: ToolContext, limit: int = 5) -> dict:
    limit = max(1, min(int(limit or 5), 10))
    rows = appointment_service.list_of_customer(ctx.db, ctx.customer.id)
    brief = [
        {
            "appt_no": r["appt_no"],
            "expected_time": r["expected_time"],
            "status": r["status_text"],
            "note": r["note"],
        }
        for r in rows[:limit]
    ]
    if not brief:
        return {"total": 0, "appointments": [], "message": "这位客户还没有提交过上门取件预约"}
    return {"total": len(rows), "appointments": brief}


_DISPATCH = {
    "query_my_orders": query_my_orders,
    "query_my_order_detail": query_my_order_detail,
    "query_my_account": query_my_account,
    "query_care_rule": query_care_rule,
    "query_price_list": query_price_list,
    "query_my_appointments": query_my_appointments,
}


def run_tool(name: str, args: dict, ctx: ToolContext) -> dict:
    """执行工具。未知工具 / 参数错都返回结构化错误，不抛异常打断对话"""
    if name not in ALLOWED_TOOLS:
        return {"error": f"不允许调用的工具：{name}"}
    func = _DISPATCH[name]
    try:
        return func(ctx, **(args or {}))
    except TypeError as exc:
        return {"error": f"参数不正确：{exc}"}
    except Exception as exc:  # noqa: BLE001 工具层兜底，任何异常都要变成可读错误
        return {"error": f"查询失败：{type(exc).__name__}"}
