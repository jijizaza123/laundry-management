"""操作日志"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Log


def add_log(db: Session, action: str, target: str = "", detail: str = "", staff_id: int | None = 1) -> None:
    db.add(Log(staff_id=staff_id, action=action, target=str(target), detail=detail))
    db.commit()


def list_logs(db: Session, limit: int = 100) -> list[dict]:
    rows = db.execute(select(Log).order_by(Log.id.desc()).limit(limit)).scalars().all()
    return [
        {
            "id": r.id,
            "staff_id": r.staff_id,
            "action": r.action,
            "target": r.target,
            "detail": r.detail,
            "created_at": r.created_at,
        }
        for r in rows
    ]
