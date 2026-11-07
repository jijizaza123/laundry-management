"""洗护知识库：结构化规则的写入与检索

设计原则：Agent 只能引用这里命中的规则；命中不到就按固定话术拒答，
不允许模型用"常识"自由发挥 —— 洗护建议说错了是要赔衣服的。
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CareRule

_KIND_ORDER = ["不可水洗", "仅手洗", "可水洗"]


def to_dict(rule: CareRule) -> dict:
    return {
        "fabric": rule.fabric,
        "aliases": [a.strip() for a in (rule.aliases or "").split(",") if a.strip()],
        "water_wash": rule.water_wash or "",
        "service": rule.service or "",
        "avoid": [a.strip() for a in (rule.avoid or "").split(";") if a.strip()],
        "reason": rule.reason or "",
        "source": rule.source or "",
    }


def list_rules(db: Session) -> list[dict]:
    rows = db.execute(select(CareRule).order_by(CareRule.id)).scalars().all()
    return [to_dict(r) for r in rows]


def _match_score(rule: CareRule, q: str) -> int:
    """精确命中给高分，别名/包含命中给低分，保证"羊绒"不会被"绒"类品类抢走"""
    names = [rule.fabric or ""] + [a.strip() for a in (rule.aliases or "").split(",") if a.strip()]
    best = 0
    for name in names:
        lower = name.lower()
        if not lower:
            continue
        if q == lower:
            best = max(best, 100 + len(lower))
        elif lower in q or q in lower:
            best = max(best, 10 + len(lower))
    return best


def lookup(db: Session, query: str | None) -> dict | None:
    """按面料/品类名检索一条规则；没有依据返回 None（调用方必须走拒答话术）"""
    q = (query or "").strip().lower()
    if not q:
        return None
    rules = db.execute(select(CareRule)).scalars().all()
    best_rule, best_score = None, 0
    for rule in rules:
        score = _match_score(rule, q)
        if score > best_score:
            best_rule, best_score = rule, score
    return to_dict(best_rule) if best_rule else None


def upsert(db: Session, payload: dict) -> dict:
    """写入或更新一条规则（按 fabric 唯一键），供种子脚本与后台维护使用"""
    fabric = (payload.get("fabric") or "").strip()
    if not fabric:
        raise ValueError("fabric 不能为空")
    rule = db.execute(select(CareRule).where(CareRule.fabric == fabric)).scalar_one_or_none()
    if not rule:
        rule = CareRule(fabric=fabric)
        db.add(rule)
    rule.aliases = payload.get("aliases", rule.aliases or "")
    rule.water_wash = payload.get("water_wash", rule.water_wash or "")
    rule.service = payload.get("service", rule.service or "")
    rule.avoid = payload.get("avoid", rule.avoid or "")
    rule.reason = payload.get("reason", rule.reason or "")
    rule.source = payload.get("source", rule.source or "")
    db.commit()
    db.refresh(rule)
    return to_dict(rule)
