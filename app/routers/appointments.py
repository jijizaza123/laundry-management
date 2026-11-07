"""管理端：上门取件预约的查询与状态推进"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, require_staff
from ..models import User
from ..schemas import AppointmentStatusRequest
from ..services import appointment_service

router = APIRouter(prefix="/api/appointments", tags=["上门取件"], dependencies=[Depends(require_staff)])


@router.get("", summary="预约列表")
def list_appointments(status: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
    return {"success": True, "data": appointment_service.list_all(db, status=status, limit=limit)}


@router.patch("/{appt_id}", summary="推进预约状态（确认/已取件/取消）")
def update_appointment(
    appt_id: int,
    payload: AppointmentStatusRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"success": True, "data": appointment_service.update_status(db, appt_id, payload.status, user.id)}
