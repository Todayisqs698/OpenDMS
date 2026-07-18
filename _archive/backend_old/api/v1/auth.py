"""
认证接口
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.models import User
from app.schemas import UserLogin, TokenResponse

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=TokenResponse)
def login(req: UserLogin, db: Session = Depends(get_db)):
    """用户登录，返回 JWT Token"""
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token(user.id, user.role)
    return {
        "access_token": token,
        "role": user.role,
        "display_name": user.display_name or user.username,
    }


@router.post("/register")
def register(username: str, password: str, role: str, display_name: str = "", db: Session = Depends(get_db)):
    """注册用户（开发阶段用，后续关闭）"""
    exist = db.query(User).filter(User.username == username).first()
    if exist:
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        display_name=display_name or username,
    )
    db.add(user)
    db.commit()
    return {"status": "ok", "user_id": user.id, "role": user.role}
