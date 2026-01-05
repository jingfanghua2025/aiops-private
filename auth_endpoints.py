from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.models.user import SessionLocal, User, UserTier, VerificationCode, RealNameStatus
from app.core.auth import create_access_token, get_password_hash, verify_password
from pydantic import BaseModel
from datetime import datetime, timedelta
import random
import string
import os
import smtplib
from email.mime.text import MIMEText
from email.header import Header

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class Token(BaseModel):
    access_token: str
    token_type: str

class RegisterSchema(BaseModel):
    username: str
    email: str
    password: str
    code: str

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(
        data={"sub": user.username, "tier": user.tier.value}
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/send-email-code")
async def send_email_code(email: str, db: Session = Depends(get_db)):
    code = ''.join(random.choices(string.digits, k=6))
    
    # 保存验证码
    new_vc = VerificationCode(target=email, code=code, type='email')
    db.add(new_vc)
    db.commit()

    # 真实发送邮件（126 SMTP）
    smtp_host = os.getenv("SMTP_HOST", "smtp.126.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)
    smtp_ssl = os.getenv("SMTP_SSL", "true").lower() in ("1", "true", "yes", "y")

    # 若未配置 SMTP，明确报错（避免继续“演示”误导）
    if not smtp_user or not smtp_pass or not smtp_from:
        raise HTTPException(status_code=500, detail="邮件服务未配置（请联系管理员设置 SMTP）")

    subject = "AIOps+ 注册验证码"
    content = f"""您的 AIOps+ 注册验证码为：{code}

验证码 10 分钟内有效，请勿泄露给他人。
如非本人操作，请忽略本邮件。"""
    msg = MIMEText(content, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = smtp_from
    msg["To"] = email

    try:
        if smtp_ssl:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
            server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_from, [email], msg.as_string())
        server.quit()
    except Exception as e:
        # 不在返回里泄露敏感配置/密码
        raise HTTPException(status_code=500, detail=f"邮件发送失败：{str(e)}")

    return {"message": f"验证码已发送至 {email}，请查收邮件"}

@router.post("/register")
async def register(reg: RegisterSchema, db: Session = Depends(get_db)):
    # 验证码校验
    vc = db.query(VerificationCode).filter(
        VerificationCode.target == reg.email,
        VerificationCode.code == reg.code,
        VerificationCode.type == 'email',
        VerificationCode.created_at > datetime.utcnow() - timedelta(minutes=10)
    ).order_by(VerificationCode.created_at.desc()).first()
    
    if not vc:
        raise HTTPException(status_code=400, detail="验证码错误或已过期")
    
    if db.query(User).filter(User.username == reg.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    if db.query(User).filter(User.email == reg.email).first():
        raise HTTPException(status_code=400, detail="邮箱已被注册")
    
    new_user = User(
        username=reg.username,
        email=reg.email,
        hashed_password=get_password_hash(reg.password),
        tier=UserTier.FREE,
        balance=1.0,
        user_type="个人用户",
        is_verified=False,
        real_name_status=RealNameStatus.NONE
    )
    db.add(new_user)
    db.commit()
    return {"message": "注册成功，请登录"}

@router.post("/wechat-login")
async def wechat_login(wechat_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.wechat_id == wechat_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="微信未绑定，请先常规登录后在个人信息中绑定")
    
    access_token = create_access_token(
        data={"sub": user.username, "tier": user.tier.value}
    )
    return {"access_token": access_token, "token_type": "bearer", "username": user.username}
