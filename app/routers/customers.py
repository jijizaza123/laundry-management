"""会员（/api/members）与客户（/api/customers）两套路径共用同一处理逻辑"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, require_staff
from ..models import User
from ..schemas import BindAccountRequest, CustomerCreate, CustomerUpdate
from ..services import auth_service, customer_service, log_service

router = APIRouter(prefix="/api", tags=["会员"], dependencies=[Depends(require_staff)])


@router.get("/customers", summary="客户列表")
def list_customers(keyword: str | None = Query(None, description="姓名或手机号模糊搜索"), db: Session = Depends(get_db)):
    return customer_service.list_customers(db, keyword=keyword)


@router.get("/members", summary="会员列表")
def list_members(keyword: str | None = Query(None, description="姓名或手机号模糊搜索"), db: Session = Depends(get_db)):
    return customer_service.list_customers(db, keyword=keyword)


@router.get("/customers/{customer_id}", summary="客户详情")
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    return customer_service.get_customer(db, customer_id)


@router.get("/members/{member_id}", summary="会员详情")
def get_member(member_id: int, db: Session = Depends(get_db)):
    return customer_service.get_customer(db, member_id)


@router.post("/customers", summary="新增客户")
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    data = customer_service.create_customer(
        db, name=payload.name, phone=payload.phone, address=payload.address, member_level=payload.member_level
    )
    log_service.add_log(db, "add_customer", payload.name, "新增客户，电话：" + payload.phone, user.id)
    return {**data, "message": "添加成功"}


@router.post("/members", summary="新增会员")
def create_member(payload: CustomerCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    data = customer_service.create_customer(
        db, name=payload.name, phone=payload.phone, address=payload.address, member_level=payload.member_level
    )
    log_service.add_log(db, "add_customer", payload.name, "新增会员，电话：" + payload.phone, user.id)
    return {**data, "message": "添加成功"}


@router.put("/customers/{customer_id}", summary="修改客户")
def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = customer_service.update_customer(
        db, customer_id, name=payload.name, phone=payload.phone, address=payload.address,
        member_level=payload.member_level, points=payload.points,
    )
    log_service.add_log(db, "update_customer", data["name"], "修改客户信息", user.id)
    return {**data, "message": "修改成功"}


@router.put("/members/{member_id}", summary="修改会员")
def update_member(
    member_id: int,
    payload: CustomerUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = customer_service.update_customer(
        db, member_id, name=payload.name, phone=payload.phone, address=payload.address,
        member_level=payload.member_level, points=payload.points,
    )
    log_service.add_log(db, "update_customer", data["name"], "修改会员信息", user.id)
    return {**data, "message": "修改成功"}


@router.post("/customers/{customer_id}/bind-account", summary="给老客户开通客户端账号")
def bind_account(
    customer_id: int,
    payload: BindAccountRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """只有门店能做的操作：核对手机号后，把历史档案绑到一个新的客户端账号上。

    客户自己注册是绑不到老档案的（否则知道手机号就能认领别人的订单/欠款）。
    """
    data = auth_service.bind_account(db, customer_id, payload.phone, payload.password, payload.name)
    log_service.add_log(db, "bind_customer_account", str(customer_id), "开通客户端账号：" + payload.phone, user.id)
    return {"success": True, "message": "已开通，客户可用手机号登录客户端", **data}


@router.get("/customers/{customer_id}/account", summary="客户账号绑定情况")
def account_status(customer_id: int, db: Session = Depends(get_db)):
    from sqlalchemy import select

    from ..models import User as UserModel

    bound = db.execute(select(UserModel).where(UserModel.customer_id == customer_id)).scalar_one_or_none()
    return {"customer_id": customer_id, "bound": bool(bound), "username": bound.username if bound else None}


@router.delete("/customers/{customer_id}", summary="删除客户")
def delete_customer(customer_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    customer_service.delete_customer(db, customer_id)
    log_service.add_log(db, "delete_customer", str(customer_id), "删除客户", user.id)
    return {"success": True, "message": "删除成功"}


@router.delete("/members/{member_id}", summary="删除会员")
def delete_member(member_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    customer_service.delete_customer(db, member_id)
    log_service.add_log(db, "delete_customer", str(member_id), "删除会员", user.id)
    return {"success": True, "message": "删除成功"}
