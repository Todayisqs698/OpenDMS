"""
JWT 认证 + RBAC 权限
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt
from app.core.config import settings


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return f"{salt}${h}"


def verify_password(plain: str, hashed: str) -> bool:
    salt, h = hashed.split("$", 1)
    return hashlib.sha256(f"{salt}:{plain}".encode()).hexdigest() == h

# 角色 → 权限映射
ROLE_PERMISSIONS = {
    "citizen": ["read:own_workorder", "create:workorder", "rate:workorder"],
    "operator": ["read:workorder", "update:workorder", "dispatch:workorder"],
    "gridworker": ["read:assigned_workorder", "update:workorder", "upload:media"],
    "admin": ["*"],  # 全部权限
}



def create_access_token(user_id: int, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "role": role, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except Exception:
        return None


def has_permission(role: str, action: str) -> bool:
    perms = ROLE_PERMISSIONS.get(role, [])
    return "*" in perms or action in perms
