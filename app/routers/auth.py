"""认证路由：管理端登录/注册 + 客户端登录/注册

两套接口分开，避免"同一个登录口按输入猜角色"带来的越权风险。
员工注册不再公开：要么带邀请码，要么由管理员在管理端建号（P0-2）。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import config
from ..db import get_db
from ..deps import require_admin
from ..models import User
from ..schemas import CustomerLoginRequest, CustomerRegisterRequest, LoginRequest, RegisterRequest
from ..services import auth_service, login_guard

router = APIRouter(prefix="/api", tags=["认证"])


@router.post("/login", summary="员工/管理员登录，返回 JWT")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    guard = login_guard.check("staff", payload.username)
    if not guard["allowed"]:
        raise HTTPException(status_code=429, detail=guard["message"])
    result = auth_service.authenticate(db, payload.username, payload.password)
    if not result:
        login_guard.record_failure("staff", payload.username)
        # 前端 login.js 依赖 message 字段
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    login_guard.reset("staff", payload.username)
    if result["user"]["role"] == "customer":
        # 客户账号不允许从管理端登录口进入
        raise HTTPException(status_code=403, detail="客户账号请从客户端登录入口登录")
    return {"success": True, "token": result["token"], "user": result["user"]}


@router.post("/register", summary="注册员工账号（需要邀请码）")
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    code = (payload.invite_code or "").strip()
    if not config.STAFF_INVITE_CODE:
        raise HTTPException(
            status_code=403, detail="员工公开注册已关闭，请让管理员在后台给你建号（或配置 LAUNDRY_STAFF_INVITE_CODE 后使用邀请码）"
        )
    if code != config.STAFF_INVITE_CODE:
        raise HTTPException(status_code=403, detail="邀请码不对，无法注册员工账号")
    user = auth_service.register(db, payload.username, payload.password, payload.name)
    return {"success": True, "message": "注册成功，请登录", "user_id": user["id"]}


@router.post("/staff/users", summary="管理员建员工账号")
def create_staff(payload: RegisterRequest, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """管理员在管理端直接开号，不需要邀请码（这条才是门店的真实做法）"""
    user = auth_service.register(db, payload.username, payload.password, payload.name)
    return {"success": True, "message": "账号已创建", "user_id": user["id"]}


@router.post("/customer/register", summary="客户注册（手机号即账号，仅限新客户）")
def customer_register(payload: CustomerRegisterRequest, db: Session = Depends(get_db)):
    info = auth_service.register_customer(db, payload.phone, payload.password, payload.name)
    return {"success": True, "message": "注册成功，请登录", **info}


@router.post("/customer/login", summary="客户登录，返回 JWT")
def customer_login(payload: CustomerLoginRequest, db: Session = Depends(get_db)):
    guard = login_guard.check("customer", payload.phone)
    if not guard["allowed"]:
        raise HTTPException(status_code=429, detail=guard["message"])
    result = auth_service.authenticate_customer(db, payload.phone, payload.password)
    if not result:
        login_guard.record_failure("customer", payload.phone)
        raise HTTPException(status_code=401, detail="手机号或密码错误")
    login_guard.reset("customer", payload.phone)
    return {"success": True, "token": result["token"], "user": result["user"]}
