"""库存业务：耗材出入库、低库存预警、按订单扣减"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import INVENTORY_PER_PIECE, INVENTORY_SUPPLY_NAME
from ..exceptions import NotFoundError, ServiceError
from ..models import Inventory, InventoryUsage, Order


def to_dict(i: Inventory) -> dict:
    return {
        "id": i.id,
        "name": i.name,
        "quantity": i.quantity or 0,
        "unit": i.unit or "件",
        "price": float(i.price or 0),
        "created_at": i.created_at,
    }


def list_inventory(db: Session) -> list[dict]:
    return [to_dict(i) for i in db.execute(select(Inventory).order_by(Inventory.id)).scalars().all()]


def low_stock(db: Session, threshold: int = 5) -> list[dict]:
    stmt = select(Inventory).where(Inventory.quantity <= threshold).order_by(Inventory.quantity)
    return [to_dict(i) for i in db.execute(stmt).scalars().all()]


def create_item(db: Session, name: str, quantity: int = 0, unit: str = "件", price: float = 0) -> dict:
    if not (name or "").strip():
        raise ServiceError("耗材名称不能为空")
    i = Inventory(name=name.strip(), quantity=int(quantity or 0), unit=unit or "件", price=float(price or 0))
    db.add(i)
    db.commit()
    db.refresh(i)
    return to_dict(i)


def stock_in(db: Session, item_id: int, quantity: int) -> dict:
    """入库"""
    if quantity <= 0:
        raise ServiceError("入库数量必须大于 0")
    i = db.get(Inventory, item_id)
    if not i:
        raise NotFoundError("库存记录不存在")
    i.quantity = (i.quantity or 0) + int(quantity)
    db.commit()
    db.refresh(i)
    return to_dict(i)


def stock_out(db: Session, item_id: int, quantity: int) -> dict:
    """出库，库存不足时拒绝"""
    if quantity <= 0:
        raise ServiceError("出库数量必须大于 0")
    i = db.get(Inventory, item_id)
    if not i:
        raise NotFoundError("库存记录不存在")
    if (i.quantity or 0) < quantity:
        raise ServiceError("库存不足，当前仅剩 " + str(i.quantity) + (i.unit or "件"))
    i.quantity = (i.quantity or 0) - int(quantity)
    db.commit()
    db.refresh(i)
    return to_dict(i)


def delete_item(db: Session, item_id: int) -> None:
    i = db.get(Inventory, item_id)
    if not i:
        raise NotFoundError("库存记录不存在")
    db.delete(i)
    db.commit()


def get_by_name(db: Session, name: str) -> Inventory | None:
    return db.execute(select(Inventory).where(Inventory.name == name)).scalar_one_or_none()


def ensure_supply_item(db: Session) -> Inventory:
    """保证"洗涤耗材"这条库存存在（不存在就以 0 建一条，便于看出"没入库"）"""
    item = get_by_name(db, INVENTORY_SUPPLY_NAME)
    if item:
        return item
    item = Inventory(name=INVENTORY_SUPPLY_NAME, quantity=0, unit="件", price=0)
    db.add(item)
    db.flush()
    return item


def consume_for_order(db: Session, order: Order) -> dict:
    """结算时按件扣耗材，并留一条用量流水。

    库存不够不阻塞结算（衣服都洗完了，不能因为账没记上就不让客户取），
    但会把"实扣数量"记清楚，管理端能看到差额。
    """
    pieces = sum(int(i.quantity or 0) for i in order.item_rows)
    need = pieces * max(INVENTORY_PER_PIECE, 0)
    item = ensure_supply_item(db)
    have = int(item.quantity or 0)
    deducted = min(have, need)
    item.quantity = have - deducted
    db.add(InventoryUsage(order_id=order.id, item_name=item.name, quantity=deducted, pieces=pieces))
    db.flush()
    return {
        "item_name": item.name,
        "pieces": pieces,
        "need": need,
        "deducted": deducted,
        "short": need - deducted,
        "left": item.quantity,
    }
