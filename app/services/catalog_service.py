"""目录业务：衣物分类 + 服务项目"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..exceptions import ConflictError, NotFoundError, ServiceError
from ..models import Category, ServiceItem


def to_category(c: Category) -> dict:
    return {"id": c.id, "name": c.name, "parent_id": c.parent_id, "description": c.description or ""}


def to_service(s: ServiceItem) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "price": float(s.price or 0),
        "unit": s.unit or "件",
        "category": s.category or "",
        "description": s.description or "",
    }


def list_categories(db: Session) -> list[dict]:
    return [to_category(c) for c in db.execute(select(Category).order_by(Category.id)).scalars().all()]


def create_category(db: Session, name: str, description: str = "") -> dict:
    if not (name or "").strip():
        raise ServiceError("分类名称不能为空")
    if db.execute(select(Category).where(Category.name == name.strip())).first():
        raise ConflictError("该分类已存在")
    c = Category(name=name.strip(), description=description, parent_id=0)
    db.add(c)
    db.commit()
    db.refresh(c)
    return to_category(c)


def list_services(db: Session) -> list[dict]:
    stmt = select(ServiceItem).order_by(ServiceItem.category, ServiceItem.id)
    return [to_service(s) for s in db.execute(stmt).scalars().all()]


def find_service(db: Session, name: str) -> dict | None:
    s = db.execute(select(ServiceItem).where(ServiceItem.name == name.strip())).scalar_one_or_none()
    return to_service(s) if s else None


def create_service(
    db: Session, name: str, price: float, unit: str = "件", category: str = "", description: str = ""
) -> dict:
    if not (name or "").strip():
        raise ServiceError("服务项目名称不能为空")
    if db.execute(select(ServiceItem).where(ServiceItem.name == name.strip())).first():
        raise ConflictError("该服务项目已存在")
    s = ServiceItem(
        name=name.strip(),
        price=float(price or 0),
        unit=unit or "件",
        category=category,
        description=description,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return to_service(s)


def update_service(db: Session, service_id: int, **fields) -> dict:
    s = db.get(ServiceItem, service_id)
    if not s:
        raise NotFoundError("服务项目不存在")
    for key in ("name", "price", "unit", "category", "description"):
        if fields.get(key) is not None:
            setattr(s, key, fields[key])
    db.commit()
    db.refresh(s)
    return to_service(s)


def delete_service(db: Session, service_id: int) -> None:
    s = db.get(ServiceItem, service_id)
    if not s:
        raise NotFoundError("服务项目不存在")
    db.delete(s)
    db.commit()


def delete_category(db: Session, category_id: int) -> None:
    c = db.get(Category, category_id)
    if not c:
        raise NotFoundError("分类不存在")
    db.delete(c)
    db.commit()

