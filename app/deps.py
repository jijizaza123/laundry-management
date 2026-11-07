"""请求级依赖：从 Bearer Token 解析当前用户，并做角色/归属校验

三层权限模型：
1. get_current_user    —— 只判断"有没有登录"
2. require_staff       —— 管理端接口：只允许 admin / staff
3. require_customer    —— 客户端接口：只允许 customer，并直接返回绑定的客户档案

注意：客户端相关接口一律不收"手机号"参数，身份只来自 token，
避免任何"传别人手机号就能查别人数据"的可能。
"""
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .db import get_db
from .models import Customer, User
from .security import decode_access_token

STAFF_ROLES = ("admin", "staff")
CUSTOMER_ROLE = "customer"


def _token_from_request(request: Request) -> str | None:
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="未登录或登录已失效")
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="登录凭证无效或已过期")
    user = db.get(User, int(payload.get("sub", -1)))
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = _token_from_request(request)
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    return db.get(User, int(payload.get("sub", -1)))


def require_staff(user: User = Depends(get_current_user)) -> User:
    """管理端接口守卫：客户账号访问一律 403"""
    if user.role not in STAFF_ROLES:
        raise HTTPException(status_code=403, detail="该功能仅限门店员工使用")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """管理员专属：建员工账号、绑定客户档案这类"能改变权限格局"的操作"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="该操作仅限管理员")
    return user


def require_customer(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Customer:
    """客户端接口守卫：身份只取 token 里的 customer_id，不接受外部传入"""
    if user.role != CUSTOMER_ROLE:
        raise HTTPException(status_code=403, detail="该功能仅限客户账号使用")
    if not user.customer_id:
        raise HTTPException(status_code=403, detail="当前账号未绑定客户档案，请联系门店")
    customer = db.get(Customer, user.customer_id)
    if not customer:
        raise HTTPException(status_code=403, detail="客户档案不存在，请联系门店")
    return customer
