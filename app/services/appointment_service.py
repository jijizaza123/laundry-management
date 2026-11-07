"""上门取件预约：与洗衣订单拆成两层单

预约单只负责"什么时候、去哪里取件"；洗什么、多少钱是取件后生成的订单。
两层拆开的好处：预约状态（待确认/已确认/已完成/已取消）不会污染五态洗涤流程。
"""
import random
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..exceptions import ConflictError, NotFoundError, ServiceError
from ..models import Appointment, Customer, now_str

VALID_STATUSES = ("pending", "confirmed", "completed", "cancelled")
STATUS_TEXT = {
    "pending": "待到店确认",
    "confirmed": "已确认，师傅按时上门",
    "completed": "已取件",
    "cancelled": "已取消",
}
STATUS_TRANSITIONS = {
    "confirmed": ("pending",),
    "completed": ("confirmed", "pending"),
    "cancelled": ("pending", "confirmed"),
}
MAX_OPEN_PER_CUSTOMER = 3


def generate_appt_no(db: Session) -> str:
    for _ in range(20):
        candidate = "A" + datetime.now().strftime("%Y%m%d%H%M%S%f")[:-3] + str(random.randint(0, 99)).zfill(2)
        if not db.execute(select(Appointment.id).where(Appointment.appt_no == candidate)).first():
            return candidate
    raise ConflictError("预约号生成失败，请重试")


def to_dict(appt: Appointment) -> dict:
    customer = getattr(appt, "customer", None)
    return {
        "id": appt.id,
        "appt_no": appt.appt_no,
        "customer_id": appt.customer_id,
        "customer_name": customer.name if customer else "",
        "customer_phone": customer.phone if customer else "",
        "expected_time": appt.expected_time,
        "address": appt.address,
        "note": appt.note or "",
        "status": appt.status,
        "status_text": STATUS_TEXT.get(appt.status, appt.status),
        "created_at": appt.created_at,
    }


def _parse_time(value: str) -> datetime:
    text = (value or "").strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ServiceError("预约时间格式不对，请用 2026-11-08 18:00 这种写法")


def create(
    db: Session,
    customer: Customer,
    expected_time: str,
    address: str,
    note: str = "",
) -> dict:
    when = _parse_time(expected_time)
    if when < datetime.now():
        raise ServiceError("预约时间不能早于现在")
    if when > datetime.now() + timedelta(days=14):
        raise ServiceError("只能预约 14 天以内的上门取件")

    addr = (address or "").strip()
    if not addr:
        raise ServiceError("上门取件需要填写取件地址")
    if len(addr) > 200:
        raise ServiceError("地址太长了，请精简到 200 字以内")

    open_count = db.execute(
        select(Appointment).where(
            Appointment.customer_id == customer.id,
            Appointment.status.in_(("pending", "confirmed")),
        )
    ).scalars().all()
    if len(open_count) >= MAX_OPEN_PER_CUSTOMER:
        raise ConflictError(f"你已有 {MAX_OPEN_PER_CUSTOMER} 个进行中的预约，等师傅联系或取消一个再来")

    appt = Appointment(
        appt_no=generate_appt_no(db),
        customer_id=customer.id,
        expected_time=when.strftime("%Y-%m-%d %H:%M"),
        address=addr,
        note=(note or "").strip()[:300],
        status="pending",
        created_at=now_str(),
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)
    return to_dict(appt)


def list_of_customer(db: Session, customer_id: int) -> list[dict]:
    rows = db.execute(
        select(Appointment).where(Appointment.customer_id == int(customer_id)).order_by(Appointment.id.desc())
    ).scalars().all()
    return [to_dict(a) for a in rows]


def list_all(db: Session, status: str | None = None, limit: int = 100) -> list[dict]:
    stmt = select(Appointment)
    if status:
        if status not in VALID_STATUSES:
            raise ServiceError("未知的预约状态：" + status)
        stmt = stmt.where(Appointment.status == status)
    stmt = stmt.order_by(Appointment.id.desc()).limit(max(1, min(int(limit or 100), 200)))
    return [to_dict(a) for a in db.execute(stmt).scalars().all()]


def update_status(db: Session, appt_id: int, target: str, staff_id: int | None = None) -> dict:
    if target not in VALID_STATUSES:
        raise ServiceError("未知的预约状态：" + target)
    appt = db.get(Appointment, appt_id)
    if not appt:
        raise NotFoundError("预约不存在")
    allowed = STATUS_TRANSITIONS.get(target, ())
    if appt.status not in allowed:
        raise ConflictError(
            f"预约当前是「{STATUS_TEXT.get(appt.status, appt.status)}」，不能改成「{STATUS_TEXT.get(target, target)}」"
        )
    appt.status = target
    if staff_id:
        appt.staff_id = staff_id
    db.commit()
    db.refresh(appt)
    return to_dict(appt)


def get_of_customer(db: Session, customer_id: int, appt_id: int) -> dict:
    appt = db.get(Appointment, appt_id)
    if not appt or appt.customer_id != int(customer_id):
        raise NotFoundError("预约不存在")
    return to_dict(appt)
