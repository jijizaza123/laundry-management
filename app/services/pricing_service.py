"""计价服务：金额一律由服务端按价目表计算，前端只提交"洗了什么、几件"

这一层同时给 HTTP 与 Agent 使用：
- Agent 不需要自己算钱，只要说明衣物明细
- 前端不能通过改 total_price 篡改金额
"""
from sqlalchemy.orm import Session

from ..config import LEVEL_NAMES, MEMBER_DISCOUNT
from ..exceptions import ServiceError
from . import catalog_service, customer_service
from .items_parser import parse_items_text


def discount_rate_for_level(level: int | None) -> float:
    return MEMBER_DISCOUNT.get(int(level or 0), 1.0)


def compute_lines(db: Session, items_detail: list[dict]) -> dict:
    """按服务项目价目表计算明细行，单价不信任调用方传值"""
    lines = []
    subtotal = 0.0
    for item in items_detail or []:
        name = (item.get("service_name") or "").strip()
        qty = int(item.get("quantity") or 0)
        if not name:
            raise ServiceError("明细缺少服务项目名称")
        if qty <= 0:
            raise ServiceError("服务数量必须大于 0：" + name)
        service = catalog_service.find_service(db, name)
        if not service:
            raise ServiceError("服务项目不存在：" + name + "，请先在服务价目表中添加")
        unit_price = round(float(service["price"]), 2)
        amount = round(unit_price * qty, 2)
        lines.append(
            {
                "category": (item.get("category") or "未分类").strip(),
                "service_name": service["name"],
                "unit": service["unit"],
                "unit_price": unit_price,
                "quantity": qty,
                "subtotal": amount,
            }
        )
        subtotal += amount
    if not lines:
        raise ServiceError("衣物明细不能为空")
    return {"lines": lines, "subtotal": round(subtotal, 2)}


def compute_lines_from_text(db: Session, items_text: str) -> dict:
    """兼容旧前端与 Agent 的自由文本入参，价格优先取价目表，取不到才用文本里的价格"""
    parsed = parse_items_text(items_text)
    lines: list[dict] = []
    subtotal = 0.0
    for row in parsed:
        service = catalog_service.find_service(db, row["service_name"]) if row["service_name"] else None
        if service:
            unit_price = round(float(service["price"]), 2)
            unit = service["unit"]
            service_name = service["name"]
        else:
            unit_price = round(float(row["unit_price"]), 2)
            unit = "件"
            service_name = row["service_name"]
        qty = int(row["quantity"] or 1)
        amount = round(unit_price * qty, 2)
        lines.append(
            {
                "category": row["category"] or "未分类",
                "service_name": service_name,
                "unit": unit,
                "unit_price": unit_price,
                "quantity": qty,
                "subtotal": amount,
            }
        )
        subtotal += amount
    if not lines:
        raise ServiceError("衣物明细不能为空")
    return {"lines": lines, "subtotal": round(subtotal, 2)}


def quote(
    db: Session,
    items_detail: list[dict] | None = None,
    items_text: str | None = None,
    customer_phone: str | None = None,
) -> dict:
    """试算：返回折前金额、会员折扣率、应收金额"""
    base = compute_lines(db, items_detail) if items_detail else compute_lines_from_text(db, items_text or "")
    level = 0
    if customer_phone:
        customer = customer_service.get_by_phone(db, customer_phone)
        if customer:
            level = customer.member_level or 0
    rate = discount_rate_for_level(level)
    total = round(base["subtotal"] * rate, 2)
    return {
        "lines": base["lines"],
        "items_text": render_items_text(base["lines"]),
        "subtotal": base["subtotal"],
        "member_level": level,
        "level_name": LEVEL_NAMES.get(level, "普通客户"),
        "discount_rate": rate,
        "discount_amount": round(base["subtotal"] - total, 2),
        "total": total,
    }


def render_items_text(lines: list[dict]) -> str:
    """生成订单展示文本（保持历史格式，便于旧按页面与小票打印）"""
    parts = []
    for line in lines:
        parts.append(
            "{cat} - {svc} (¥{price:.2f}/{unit}) x{qty}".format(
                cat=line["category"],
                svc=line["service_name"],
                price=float(line["unit_price"]),
                unit=line.get("unit") or "件",
                qty=line["quantity"],
            )
        )
    return "\n".join(parts)
