"""密码哈希与 JWT"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, SECRET_KEY


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(raw: str, stored: str) -> bool:
    """兼容历史明文密码：bcrypt 校验失败时按明文比对"""
    if not stored:
        return False
    if stored.startswith("$2"):
        try:
            return bcrypt.checkpw(raw.encode("utf-8"), stored.encode("utf-8"))
        except ValueError:
            return False
    return raw == stored


def create_access_token(user_id: int, role: str, customer_id: int | None = None) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "cid": customer_id,          # 客户身份唯一来源，服务端据此过滤数据
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
