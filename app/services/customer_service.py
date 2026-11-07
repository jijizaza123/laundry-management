"""会员/客户业务：查询、建档、积分累计、等级升级"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import LEVEL_NAMES, LEVEL_THRESHOLDS, POINTS_PER_YUAN
from ..exceptions import ConflictError, NotFoundError, ServiceError
from ..models import Customer


def level_name(level: int | None) -> str:
    return LEVEL_NAMES.get(int(level or 0), "普通客户")


def level_from_points(points: int) -> int:
    for threshold, level in LEVEL_THRESHOLDS:
        if points >= threshold:
            return level
    return 0


def to_dict(c: Customer) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "phone": c.phone,
        "address": c.address or "",
        "member_level": c.member_level or 0,
        "points": c.points or 0,
        "created_at": c.created_at,
        "level_name": level_name(c.member_level),
    }


def list_customers(db: Session, keyword: str | None = None) -> list[dict]:
    stmt = select(Customer)
    if keyword:
        kw = "%" + keyword.strip() + "%"
        stmt = stmt.where((Customer.name.like(kw)) | (Customer.phone.like(kw)))
    stmt = stmt.order_by(Customer.id.desc())
    return [to_dict(c) for c in db.execute(stmt).scalars().all()]


def get_customer(db: Session, customer_id: int) -> dict:
    c = db.get(Customer, customer_id)
    if not c:
        raise NotFoundError("客户不存在")
    return to_dict(c)


def get_by_phone(db: Session, phone: str) -> Customer | None:
    return db.execute(select(Customer).where(Customer.phone == phone.strip())).scalar_one_or_none()


def create_customer(
    db: Session,
    name: str,
    phone: str,
    address: str = "",
    member_level: int = 0,
    points: int = 0,
) -> dict:
    name = (name or "").strip()
    phone = (phone or "").strip()
    if not name:
        raise ServiceError("客户姓名不能为空")
    if not phone:
        raise ServiceError("手机号不能为空")
    if get_by_phone(db, phone):
        raise ConflictError("该手机号已存在")
    c = Customer(
        name=name,
        phone=phone,
        address=address or "",
        member_level=int(member_level or 0),
        points=int(points or 0),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return to_dict(c)


def get_or_create_by_phone(db: Session, name: str, phone: str) -> Customer:
    existing = get_by_phone(db, phone)
    if existing:
        return existing
    c = Customer(name=(name or "").strip() or phone.strip(), phone=phone.strip(), address="", member_level=0, points=0)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def update_customer(
    db: Session,
    customer_id: int,
    name: str | None = None,
    phone: str | None = None,
    address: str | None = None,
    member_level: int | None = None,
    points: int | None = None,
) -> dict:
    c = db.get(Customer, customer_id)
    if not c:
        raise NotFoundError("客户不存在")
    if phone and phone.strip() != c.phone:
        if get_by_phone(db, phone):
            raise ConflictError("该手机号已被其他会员使用")
        c.phone = phone.strip()
    if name:
        c.name = name.strip()
    if address is not None:
        c.address = address
    if member_level is not None:
        c.member_level = int(member_level)
    if points is not None:
        c.points = int(points)
    db.commit()
    db.refresh(c)
    return to_dict(c)


def delete_customer(db: Session, customer_id: int) -> None:
    c = db.get(Customer, customer_id)
    if not c:
        raise NotFoundError("客户不存在")
    db.delete(c)
    db.commit()


def add_points_for_amount(db: Session, customer: Customer, amount: float) -> dict:
    """按消费金额累计积分，并自动升级（只升不降）"""
    gained = int(round(float(amount) * POINTS_PER_YUAN))
    if gained > 0:
        customer.points = (customer.points or 0) + gained
    new_level = level_from_points(customer.points or 0)
    if new_level > (customer.member_level or 0):
        customer.member_level = new_level
    db.commit()
    db.refresh(customer)
    return {"points_gained": gained, "points": customer.points, "member_level": customer.member_level}

