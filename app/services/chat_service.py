"""Agent 会话存储：让对话刷新后还在，同时留下可评估的样本

按 session_key 隔离（customer:1 / staff:1），不按"人"存全局历史，
既是隐私边界，也让评估能按角色取样本。
"""
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import ChatMessage, now_str


def session_key_customer(customer_id: int) -> str:
    return f"customer:{int(customer_id)}"


def session_key_staff(user_id: int) -> str:
    return f"staff:{int(user_id)}"


def append(db: Session, session_key: str, role: str, content: str, tools_used: list[str] | None = None) -> None:
    if role not in ("user", "assistant"):
        return
    db.add(
        ChatMessage(
            session_key=session_key,
            role=role,
            content=(content or "")[:2000],
            tools_used=",".join(tools_used or [])[:200],
            created_at=now_str(),
        )
    )
    db.commit()


def history(db: Session, session_key: str, limit: int = 12) -> list[dict]:
    rows = (
        db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_key == session_key)
            .order_by(ChatMessage.id.desc())
            .limit(max(1, min(int(limit or 12), 50)))
        )
        .scalars()
        .all()
    )
    rows.reverse()
    return [{"role": r.role, "content": r.content, "tools_used": r.tools_used or ""} for r in rows]


def clear(db: Session, session_key: str) -> None:
    db.execute(delete(ChatMessage).where(ChatMessage.session_key == session_key))
    db.commit()
