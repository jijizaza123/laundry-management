"""Agent 调用指标：回答要能讲"成本与延迟"，就得先有数据

每轮对话落一条：轮次、工具、耗时、是否报错。管理端 /api/staff/metrics 汇总。
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AgentMetric, now_str


def record(
    db: Session,
    session_key: str,
    side: str,
    question: str,
    answer: str,
    rounds: int,
    tools_used: list[str] | None,
    elapsed_ms: int,
    ok: bool = True,
    engine: str = "loop",
) -> None:
    db.add(
        AgentMetric(
            session_key=session_key,
            side=side,
            engine=engine,
            question_chars=len(question or ""),
            question=(question or "")[:255],
            answer_chars=len(answer or ""),
            rounds=int(rounds or 0),
            tools_used=",".join(tools_used or [])[:255],
            elapsed_ms=int(elapsed_ms or 0),
            ok=1 if ok else 0,
            created_at=now_str(),
        )
    )
    db.commit()


def _percentile(values: list[int], ratio: float) -> int:
    if not values:
        return 0
    values = sorted(values)
    idx = min(len(values) - 1, max(0, int(round((len(values) - 1) * ratio))))
    return values[idx]


def summary(db: Session, days: int = 7) -> dict:
    from datetime import datetime, timedelta

    end = datetime.now()
    start = end - timedelta(days=max(1, int(days)))
    since = start.strftime("%Y-%m-%d 00:00:00")
    rows = (
        db.execute(select(AgentMetric).where(AgentMetric.created_at >= since).order_by(AgentMetric.id.desc()))
        .scalars()
        .all()
    )
    data = []
    for side in ("customer", "staff"):
        sub = [r for r in rows if r.side == side]
        lats = [int(r.elapsed_ms or 0) for r in sub]
        errs = len([r for r in sub if not r.ok])
        rounds = [int(r.rounds or 0) for r in sub]
        data.append(
            {
                "side": side,
                "calls": len(sub),
                "errors": errs,
                "error_rate": round(errs / len(sub), 4) if sub else 0.0,
                "avg_ms": int(sum(lats) / len(lats)) if lats else 0,
                "p50_ms": _percentile(lats, 0.5),
                "p95_ms": _percentile(lats, 0.95),
                "max_ms": max(lats) if lats else 0,
                "avg_rounds": round(sum(rounds) / len(rounds), 2) if rounds else 0.0,
                "tool_calls": sum(len([t for t in (r.tools_used or "").split(",") if t]) for r in sub),
            }
        )
    return {
        "days": days,
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": end.strftime("%Y-%m-%d"),
        "sides": data,
        "recent": [_to_dict(r) for r in rows[:20]],
    }


def _to_dict(r: AgentMetric) -> dict:
    return {
        "id": r.id,
        "side": r.side,
        "engine": r.engine,
        "question": r.question or "",
        "rounds": r.rounds,
        "tools": [t for t in (r.tools_used or "").split(",") if t],
        "elapsed_ms": r.elapsed_ms,
        "ok": bool(r.ok),
        "created_at": r.created_at,
    }
