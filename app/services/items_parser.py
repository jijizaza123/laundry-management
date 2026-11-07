"""衣物明细文本解析（独立模块，避免 pricing 与 order 互相导入）"""
import re

ITEM_LINE_RE = re.compile(
    r"^(?P<category>.+?)\s*-\s*(?P<service>.+?)\s*\(¥\s*(?P<price>[\d.]+)\s*/\s*(?P<unit>[^)]*)\)\s*x\s*(?P<qty>\d+)"
)


def parse_items_text(items_text: str) -> list[dict]:
    """把 "上衣 - 普通洗 (¥20/件) x3" 这类展示文本解析成结构化明细"""
    result = []
    for line in (items_text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        m = ITEM_LINE_RE.match(line)
        if m:
            price = float(m.group("price"))
            qty = int(m.group("qty"))
            result.append(
                {
                    "category": m.group("category").strip(),
                    "service_name": m.group("service").strip(),
                    "unit_price": price,
                    "quantity": qty,
                    "subtotal": round(price * qty, 2),
                }
            )
        else:
            # 解析不了的行不丢，按零价回退，避免历史数据丢失
            result.append(
                {"category": "", "service_name": line, "unit_price": 0.0, "quantity": 1, "subtotal": 0.0}
            )
    return result
