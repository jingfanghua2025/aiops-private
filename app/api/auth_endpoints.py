from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models.user import SessionLocal, User, UserTier, VerificationCode, RealNameStatus
from app.core.auth import create_access_token, get_password_hash, verify_password
from app.services.sms_service import aliyun_sms_service
from pydantic import BaseModel
from datetime import datetime, timedelta
import random
import string
import os
import re
import smtplib
from email.mime.text import MIMEText
from email.header import Header

router = APIRouter()


def _send_email(to_email: str, subject: str, content: str):
    smtp_host = os.getenv("SMTP_HOST", "smtp.126.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)
    smtp_ssl = os.getenv("SMTP_SSL", "true").lower() in ("1", "true", "yes", "y")

    if not smtp_user or not smtp_pass or not smtp_from:
        raise HTTPException(status_code=500, detail="邮件服务未配置（请联系管理员设置 SMTP）")

    msg = MIMEText(content, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = smtp_from
    msg["To"] = to_email

    try:
        if smtp_ssl:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
            server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_from, [to_email], msg.as_string())
        server.quit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"邮件发送失败：{str(e)}")


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
    """
    统一登录接口：支持账号/手机号/微信登录
    form_data.username 可以是：用户名、手机号、微信ID
    """
    login_identifier = form_data.username.strip()
    user = None
    
    # 1. 先尝试用户名登录
    user = db.query(User).filter(User.username == login_identifier).first()
    
    # 2. 如果用户名不存在，尝试手机号登录
    if not user:
        user = db.query(User).filter(User.phone == login_identifier).first()
    
    # 3. 如果手机号也不存在，尝试微信ID登录（需要密码为空或特殊标识）
    if not user:
        user = db.query(User).filter(User.wechat_id == login_identifier).first()
        # 微信登录通常不需要密码，但如果提供了密码，也需要验证
        if user and form_data.password and form_data.password != "":
            if not verify_password(form_data.password, user.hashed_password):
                user = None
    
    # 验证用户和密码
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 微信登录可以无密码，其他方式必须验证密码
    if user.wechat_id == login_identifier and (not form_data.password or form_data.password == ""):
        # 微信登录，无需密码验证
        pass
    elif not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="密码错误",
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



class ResetCodeSchema(BaseModel):
    channel: str  # email / sms
    target: str   # email or phone

class ResetPasswordSchema(BaseModel):
    channel: str  # email / sms
    target: str   # email or phone
    code: str
    new_password: str


@router.post("/send-reset-code")
async def send_reset_code(req: ResetCodeSchema, db: Session = Depends(get_db)):
    channel = (req.channel or '').strip().lower()
    target = (req.target or '').strip()
    if channel not in ('email','sms'):
        raise HTTPException(status_code=400, detail='channel 仅支持 email / sms')

    # 频控：同一 target 60s 一次
    vc_type = 'email_reset' if channel == 'email' else 'sms_reset'
    latest = db.query(VerificationCode).filter(
        VerificationCode.target == target,
        VerificationCode.type == vc_type,
        VerificationCode.created_at > datetime.utcnow() - timedelta(seconds=60)
    ).order_by(VerificationCode.created_at.desc()).first()
    if latest:
        raise HTTPException(status_code=429, detail='请求过于频繁，请稍后再试')

    # target 校验 + 用户存在校验
    if channel == 'email':
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", target):
            raise HTTPException(status_code=400, detail='邮箱格式不正确')
        user = db.query(User).filter(User.email == target).first()
        if not user:
            # 不泄露是否存在：统一提示已发送
            return {"message": "验证码已发送（如该邮箱已注册）"}
    else:
        if not re.fullmatch(r"1[3-9]\d{9}", target):
            raise HTTPException(status_code=400, detail='手机号格式不正确')
        user = db.query(User).filter(User.phone == target).first()
        if not user:
            return {"message": "验证码已发送（如该手机号已绑定账号）"}

    code = ''.join(random.choices(string.digits, k=6))

    # 发送
    if channel == 'email':
        subject = 'AIOps+ 找回密码验证码'
        content = f"""您的 AIOps+ 找回密码验证码为：{code}

验证码 10 分钟内有效，请勿泄露给他人。
如非本人操作，请忽略本邮件。"""
        _send_email(target, subject, content)
    else:
        try:
            aliyun_sms_service.send_verification_code(phone=target, code=code)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    db.add(VerificationCode(target=target, code=code, type=vc_type))
    db.commit()

    return {"message": "验证码已发送"}


@router.post("/reset-password")
async def reset_password(req: ResetPasswordSchema, db: Session = Depends(get_db)):
    channel = (req.channel or '').strip().lower()
    target = (req.target or '').strip()
    code = (req.code or '').strip()
    new_password = (req.new_password or '').strip()

    if channel not in ('email','sms'):
        raise HTTPException(status_code=400, detail='channel 仅支持 email / sms')
    if not code:
        raise HTTPException(status_code=400, detail='验证码不能为空')
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail='新密码至少 8 位')

    vc_type = 'email_reset' if channel == 'email' else 'sms_reset'

    # 找用户
    if channel == 'email':
        user = db.query(User).filter(User.email == target).first()
    else:
        user = db.query(User).filter(User.phone == target).first()
    if not user:
        raise HTTPException(status_code=400, detail='账号不存在或未绑定该方式')

    # 校验验证码（10分钟）
    vc = db.query(VerificationCode).filter(
        VerificationCode.target == target,
        VerificationCode.code == code,
        VerificationCode.type == vc_type,
        VerificationCode.created_at > datetime.utcnow() - timedelta(minutes=10)
    ).order_by(VerificationCode.created_at.desc()).first()

    if not vc:
        raise HTTPException(status_code=400, detail='验证码错误或已过期')

    user.hashed_password = get_password_hash(new_password)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=500, detail='重置失败，请稍后重试')

    return {"message": "密码已重置，请使用新密码登录"}
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
            balance=300.0,  # 新用户默认300个算力值
        user_type="个人用户",
        is_verified=False,
        real_name_status=RealNameStatus.NONE
    )
    db.add(new_user)
    db.commit()
    return {"message": "注册成功，请登录"}

@router.post("/login-sms")
async def login_sms(phone: str, code: str, db: Session = Depends(get_db)):
    """短信验证码登录"""
    phone = phone.strip()
    if not re.fullmatch(r"1[3-9]\d{9}", phone):
        raise HTTPException(status_code=400, detail="手机号格式不正确")
    
    # 验证验证码
    vc = db.query(VerificationCode).filter(
        VerificationCode.target == phone,
        VerificationCode.code == code,
        VerificationCode.type == 'sms',
        VerificationCode.created_at > datetime.utcnow() - timedelta(minutes=10)
    ).order_by(VerificationCode.created_at.desc()).first()
    
    if not vc:
        raise HTTPException(status_code=400, detail="验证码错误或已过期")
    
    # 查找用户
    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        raise HTTPException(status_code=404, detail="该手机号未绑定账号")
    
    access_token = create_access_token(
        data={"sub": user.username, "tier": user.tier.value}
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/wechat-login")
async def wechat_login(wechat_id: str, db: Session = Depends(get_db)):
    """微信登录（保留原有接口，兼容性）"""
    user = db.query(User).filter(User.wechat_id == wechat_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="微信未绑定，请先常规登录后在个人信息中绑定")
    
    access_token = create_access_token(
        data={"sub": user.username, "tier": user.tier.value}
    )
    return {"access_token": access_token, "token_type": "bearer", "username": user.username}
