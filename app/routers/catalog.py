"""目录路由：衣物分类与服务项目"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, require_staff
from ..schemas import CategoryCreate, ServiceItemCreate
from ..services import catalog_service

router = APIRouter(prefix="/api", tags=["目录"], dependencies=[Depends(require_staff)])


@router.get("/categories", summary="衣物分类列表")
def list_categories(db: Session = Depends(get_db)):
    return catalog_service.list_categories(db)


@router.post("/categories", summary="新增衣物分类")
def create_category(payload: CategoryCreate, db: Session = Depends(get_db)):
    return catalog_service.create_category(db, payload.name, payload.description)


@router.delete("/categories/{category_id}", summary="删除衣物分类")
def delete_category(category_id: int, db: Session = Depends(get_db)):
    catalog_service.delete_category(db, category_id)
    return {"success": True, "message": "删除成功"}


@router.get("/services", summary="服务项目列表（含单价）")
def list_services(db: Session = Depends(get_db)):
    return catalog_service.list_services(db)


@router.post("/services", summary="新增服务项目")
def create_service(payload: ServiceItemCreate, db: Session = Depends(get_db)):
    return catalog_service.create_service(
        db, payload.name, payload.price, payload.unit, payload.category, payload.description
    )


@router.put("/services/{service_id}", summary="修改服务项目")
def update_service(service_id: int, payload: ServiceItemCreate, db: Session = Depends(get_db)):
    return catalog_service.update_service(
        db, service_id, name=payload.name, price=payload.price, unit=payload.unit,
        category=payload.category, description=payload.description,
    )


@router.delete("/services/{service_id}", summary="删除服务项目")
def delete_service(service_id: int, db: Session = Depends(get_db)):
    catalog_service.delete_service(db, service_id)
    return {"success": True, "message": "删除成功"}
