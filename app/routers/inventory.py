"""库存与日志路由"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, require_staff
from ..schemas import InventoryCreate
from ..services import inventory_service, log_service

router = APIRouter(prefix="/api", tags=["库存"], dependencies=[Depends(require_staff)])


@router.get("/inventory", summary="库存列表")
def list_inventory(db: Session = Depends(get_db)):
    return inventory_service.list_inventory(db)


@router.get("/inventory/low-stock", summary="低库存预警")
def low_stock(threshold: int = Query(5, ge=0), db: Session = Depends(get_db)):
    return inventory_service.low_stock(db, threshold)


@router.post("/inventory", summary="新增耗材")
def create_item(payload: InventoryCreate, db: Session = Depends(get_db)):
    return inventory_service.create_item(db, payload.name, payload.quantity, payload.unit, payload.price)


@router.post("/inventory/{item_id}/in", summary="入库")
def stock_in(item_id: int, quantity: int = Query(..., gt=0, description="入库数量"), db: Session = Depends(get_db)):
    return inventory_service.stock_in(db, item_id, quantity)


@router.post("/inventory/{item_id}/out", summary="出库")
def stock_out(item_id: int, quantity: int = Query(..., gt=0, description="出库数量"), db: Session = Depends(get_db)):
    return inventory_service.stock_out(db, item_id, quantity)


@router.delete("/inventory/{item_id}", summary="删除耗材")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    inventory_service.delete_item(db, item_id)
    return {"success": True, "message": "删除成功"}


@router.get("/logs", summary="操作日志")
def list_logs(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    return log_service.list_logs(db, limit)
