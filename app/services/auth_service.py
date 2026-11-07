"""认证业务：员工登录/注册、客户登录/注册、历史明文密码升级

两套身份共用 users 表，靠 role 区分：
- admin / staff  → 管理端
- customer       → 客户端，且必须绑定 customer_id 指向 customers 档案
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..exceptions import ConflictError, NotFoundError, ServiceError
from ..models import Customer, User
from ..security import create_access_token, hash_password, verify_password
from . import customer_service

CUSTOMER_ROLE = "customer"


def authenticate(db: Session, username: str, password: str) -> dict | None:
    user = db.execute(select(User).where(User.username == (username or "").strip())).scalar_one_or_none()
    if not user or not verify_password(password or "", user.password):
        return None
    # 历史明文密码首次登录即升级为 bcrypt
    if not (user.password or "").startswith("$2"):
        user.password = hash_password(password)
        db.commit()
    token = create_access_token(user.id, user.role, user.customer_id)
    return {
        "token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "name": user.name,
            "customer_id": user.customer_id,
        },
    }


def register(db: Session, username: str, password: str, name: str, role: str = "staff") -> dict:
    username = (username or "").strip()
    if db.execute(select(User).where(User.username == username)).scalar_one_or_none():
        raise ConflictError("用户名已存在")
    user = User(username=username, password=hash_password(password), role=role, name=(name or "").strip())
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username, "role": user.role, "name": user.name}


# ---------------- 客户账号 ----------------


MIN_PASSWORD_LEN = 6


def _check_password(password: str) -> str:
    """密码策略：至少 6 位，且不能是纯数字（P0 顺手补的一条）"""
    password = (password or "").strip()
    if len(password) < MIN_PASSWORD_LEN:
        raise ServiceError("密码至少 " + str(MIN_PASSWORD_LEN) + " 位")
    if password.isdigit():
        raise ServiceError("密码不能是纯数字，请加字母")
    return password


def register_customer(db: Session, phone: str, password: str, name: str | None = None) -> dict:
    """客户自助注册：手机号即账号，只允许"从零新建档案"。

    P0-3：以前是"手机号在 customers 里存在就把号绑到那条档案"，等于知道别人手机号
    就能接管他的历史订单、欠款、会员积分。现在这种做法取消了：老客户要开网上账号，
    必须由门店在管理端「帮客户开通账号」（bind_account），身份由门店核验。
    """
    phone = (phone or "").strip()
    if not phone:
        raise ServiceError("手机号不能为空")
    password = _check_password(password)

    exists = db.execute(select(User).where(User.username == phone)).scalar_one_or_none()
    if exists:
        raise ConflictError("该手机号已注册，请直接登录")

    customer = customer_service.get_by_phone(db, phone)
    if customer:
        raise ConflictError("该手机号有到店记录，请让门店在后台帮你开通网上账号（避免别人拿手机号认领你的订单）")

    customer = Customer(
        name=(name or "").strip() or phone,
        phone=phone,
        address="",
        member_level=0,
        points=0,
    )
    db.add(customer)
    db.flush()

    user = User(
        username=phone,
        password=hash_password(password),
        role=CUSTOMER_ROLE,
        name=customer.name,
        customer_id=customer.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {
        "user_id": user.id,
        "customer_id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
        "existing_archive": False,
    }


def bind_account(db: Session, customer_id: int, phone: str, password: str, name: str | None = None) -> dict:
    """门店给已有档案的老客户开通客户端账号（唯一能"绑定历史档案"的入口）"""
    customer = db.get(Customer, int(customer_id))
    if not customer:
        raise NotFoundError("客户档案不存在")
    phone = (phone or "").strip()
    if phone != (customer.phone or "").strip():
        raise ServiceError("手机号与档案不一致，请核对后再开通")
    password = _check_password(password)
    if db.execute(select(User).where(User.username == phone)).scalar_one_or_none():
        raise ConflictError("该手机号已注册，无需重复开通")
    if db.execute(select(User).where(User.customer_id == customer.id)).scalar_one_or_none():
        raise ConflictError("该客户档案已绑定账号")

    user = User(
        username=phone,
        password=hash_password(password),
        role=CUSTOMER_ROLE,
        name=(name or customer.name or phone),
        customer_id=customer.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"user_id": user.id, "customer_id": customer.id, "phone": phone, "name": user.name}


def authenticate_customer(db: Session, phone: str, password: str) -> dict | None:
    phone = (phone or "").strip()
    user = db.execute(select(User).where(User.username == phone, User.role == CUSTOMER_ROLE)).scalar_one_or_none()
    if not user or not verify_password(password or "", user.password):
        return None
    if not (user.password or "").startswith("$2"):
        user.password = hash_password(password)
        db.commit()
    customer = db.get(Customer, user.customer_id) if user.customer_id else None
    if not customer:
        return None
    token = create_access_token(user.id, user.role, user.customer_id)
    return {
        "token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "name": customer.name,
            "customer_id": customer.id,
            "member_level": customer.member_level or 0,
        },
    }


def encrypt_existing_passwords(db: Session) -> int:
    """启动时把库里的明文密码统一升级为 bcrypt，返回升级条数"""
    changed = 0
    for user in db.execute(select(User)).scalars().all():
        if user.password and not user.password.startswith("$2"):
            user.password = hash_password(user.password)
            changed += 1
    if changed:
        db.commit()
    return changed
