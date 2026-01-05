from starlette.concurrency import run_in_threadpool
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, status, Form, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from app.models.user import (
    SessionLocal,
    User,
    SSHHost,
    UsageLog,
    UserTier,
    PrivateKB,
    ChatSession,
    VerificationCode,
    RealNameStatus,
    PaymentOrder,
    PaymentStatus,
    PaymentMethod,
    EnterpriseProfile,
    VerificationStatus,
)
from app.services.rag_service import RAGService
from app.services.enhanced_rag_service import EnhancedRAGService
from app.services.script_service import ScriptService
from app.services.diagnosis_service import DiagnosisService
from app.services.ssh_service import SSHService
from app.services.enhanced_ssh_service import EnhancedSSHService
from app.core.auth import get_current_user_tier, oauth2_scheme, SECRET_KEY, ALGORITHM, get_password_hash, verify_password
from app.services.payment_service import payment_service
from app.services.sms_service import aliyun_sms_service
from pydantic import BaseModel
from jose import jwt
from datetime import datetime, timedelta
from typing import Optional
import json
import requests
from bs4 import BeautifulSoup
import os
import shutil
import random
import string
import logging
import re

router = APIRouter()
rag_service = RAGService()
enhanced_rag_service = EnhancedRAGService()  # 增强的RAG服务（支持多轮对话）
script_service = ScriptService()
diagnosis_service = DiagnosisService()
ssh_service = SSHService()
enhanced_ssh_service = EnhancedSSHService()  # 增强的SSH服务（更精确）
logger = logging.getLogger(__name__)

UPLOAD_DIR = "/root/ops-gpt/backend/static/uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# --- 计费与点数规则（单位：算力点，参考DeepSeek和豆包API成本制定） ---
# 参考成本：
# - DeepSeek Chat: 约 $0.14/1M tokens (输入) + $0.28/1M tokens (输出)
# - 豆包 Qwen-Turbo: 约 ¥0.008/1K tokens (输入+输出)
# - 平均每次排障计划生成约消耗 2000-5000 tokens，成本约 ¥0.02-0.04
# 
# 收费规则：
# - 方案咨询（qa）：永久免费
# - 代码编写（code）：永久免费  
# - 排障&部署（ops）：收费，每次生成计划消耗算力点
#
# 算力点价值：1点 = ¥0.01（包含API成本+服务成本+合理利润）
POINT_VALUE_RMB = 0.01
TROUBLESHOOT_BASE_POINTS = 5          # 标准一次排障计划消耗5点（约¥0.05，覆盖API成本）
EXTRA_RETRY_POINTS = 3                # 额外自动修正消耗3点
LONG_CONTEXT_POINTS = 2               # 超长上下文/日志附加点

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        user = db.query(User).filter(User.username == username).first()
        if user is None: raise HTTPException(status_code=401)
        return user
    except: raise HTTPException(status_code=401)

# --- Schemas ---
class SSHHostSchema(BaseModel):
    name: str
    ip: str
    port: int = 22
    username: str
    password: Optional[str] = None
    private_key: Optional[str] = None
    auth_type: Optional[str] = 'password'

class KBItemSchema(BaseModel):
    title: str
    content: str

class SessionSchema(BaseModel):
    title: str
    content: str

class ProposeSchema(BaseModel):
    host_id: int
    task: str
    conversation_id: Optional[str] = None  # 对话ID（用于多轮对话）

class ExecSchema(BaseModel):
    host_id: int
    command: str

class PasswordChangeSchema(BaseModel):
    old_password: str
    new_password: str

class RechargeOrderSchema(BaseModel):
    amount: float
    method: str
    return_url: str | None = None

# --- User Profile & Verification ---
def mask_sensitive_info(text: str) -> str:
    """脱敏处理：将用户名、密码等敏感信息替换为*号"""
    if not text:
        return text
    
    import re
    result = text
    
    # 1. 匹配 "密码: xxx" 或 "密码=xxx" 这种中文格式（优先匹配，因为更常见）
    # 匹配密码后面的所有内容，直到遇到空格、换行或字符串结束
    # 使用非贪婪匹配，但确保匹配到完整的密码值
    result = re.sub(r'(?i)(密码|口令)\s*[=:：]\s*([^\s]+)', r'\1=****', result)
    
    # 2. 匹配 "用户名: xxx" 或 "用户名=xxx" 这种中文格式
    result = re.sub(r'(?i)(用户名|账号)\s*[=:：]\s*([^\s]+)', r'\1=****', result)
    
    # 3. 匹配 password/pwd/pass=xxx 或 password/pwd/pass: xxx
    result = re.sub(r'(?i)(password|pwd|pass)\s*[=:]\s*([^\s]+)', r'\1=****', result)
    
    # 4. 匹配 username/user=xxx 或 username/user: xxx
    result = re.sub(r'(?i)(username|user)\s*[=:]\s*([^\s]+)', r'\1=****', result)
    
    # 5. 匹配 api_key/key=xxx 或 api_key/key: xxx
    result = re.sub(r'(?i)(api[_-]?key|key)\s*[=:]\s*([^\s]+)', r'\1=****', result)
    
    # 6. 匹配 token/access_token=xxx 或 token/access_token: xxx
    result = re.sub(r'(?i)(token|access[_-]?token)\s*[=:]\s*([^\s]+)', r'\1=****', result)
    
    # 7. 匹配 SSH 命令中的密码：ssh user@host 密码: xxx 或 ssh host user 密码: xxx
    result = re.sub(r'(?i)(ssh\s+[^\s]+\s+[^\s]+\s+)(密码|password)\s*[=:：]\s*([^\s\n]+)', r'\1\2=****', result)
    
    # 8. 匹配 "root 密码: xxx" 这种格式
    result = re.sub(r'(?i)(root|admin|user)\s+(密码|password)\s*[=:：]\s*([^\s\n]+)', r'\1 \2=****', result)
    
    return result


@router.get("/user/profile")
async def get_profile(user: User = Depends(get_current_user)):
    return {
        "username": user.username,
        "email": user.email,
        "phone": user.phone,
        "user_type": user.user_type,
        "is_admin": user.is_admin if hasattr(user, 'is_admin') else False,
        "real_name_status": user.real_name_status.value,
        "is_wechat_bound": user.is_wechat_bound,
        "created_at": user.created_at.strftime("%Y-%m-%d"),
        "balance": round(user.balance, 2),
        "business_license_url": user.business_license_url
    }

@router.post("/user/send-sms")
async def send_sms_code(phone: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    phone = (phone or '').strip()
    # 简单手机号校验（中国大陆）
    if not re.fullmatch(r"1[3-9]\d{9}", phone):
        raise HTTPException(status_code=400, detail="手机号格式不正确")

    # 发送频控：60s 内同一手机号只允许发送一次
    latest = db.query(VerificationCode).filter(
        VerificationCode.target == phone,
        VerificationCode.type == 'sms',
        VerificationCode.created_at > datetime.utcnow() - timedelta(seconds=60)
    ).order_by(VerificationCode.created_at.desc()).first()
    if latest:
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    code = ''.join(random.choices(string.digits, k=6))

    try:
        aliyun_sms_service.send_verification_code(phone=phone, code=code)
    except Exception as exc:
        logger.exception('短信发送失败 phone=%s err=%s', phone[:3] + '****' + phone[-4:], exc)
        raise HTTPException(status_code=500, detail=str(exc))

    # 仅在短信发送成功后落库，避免“发送失败但验证码可用”的脏数据
    new_vc = VerificationCode(target=phone, code=code, type='sms')
    db.add(new_vc)
    db.commit()

    return {"message": "验证码已发送"}

@router.post("/user/verify-personal")
async def verify_personal(phone: str, code: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # 已实名则不允许重复认证（避免从企业/个人状态来回切换）
    if user.real_name_status not in [RealNameStatus.NONE, RealNameStatus.PERSONAL_PENDING]:
        st = user.real_name_status.value
        if "enterprise" in st:
            return {"message": "已完成企业实名认证，无需个人实名认证"}
        elif st == RealNameStatus.PERSONAL.value:
            return {"message": "已完成个人实名认证，无需重复认证"}

    phone = (phone or '').strip()
    if not re.fullmatch(r"1[3-9]\d{9}", phone):
        raise HTTPException(status_code=400, detail="手机号格式不正确")

    # 手机号不可被其他账号占用
    exists = db.query(User).filter(User.phone == phone, User.id != user.id).first()
    if exists:
        raise HTTPException(status_code=400, detail="该手机号已被其他账号绑定")

    vc = db.query(VerificationCode).filter(
        VerificationCode.target == phone,
        VerificationCode.code == code,
        VerificationCode.type == 'sms',
        VerificationCode.created_at > datetime.utcnow() - timedelta(minutes=10)
    ).order_by(VerificationCode.created_at.desc()).first()

    if not vc:
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    user.phone = phone
    user.real_name_status = RealNameStatus.PERSONAL  # 个人认证直接通过，无需审核
    user.is_verified = True

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="该手机号已被其他账号绑定")

    return {"message": "个人实名认证成功"}

@router.post("/user/verify-enterprise")
async def verify_enterprise(
    company_name: str = Form(...),
    license_no: str = Form(...),
    contact_phone: str = Form(...),
    phone_code: str = Form(...),
    wechat_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 已实名则不允许重复认证
    if user.real_name_status not in [RealNameStatus.NONE, RealNameStatus.ENTERPRISE_PENDING]:
        st = user.real_name_status.value
        if "enterprise" in st and st == RealNameStatus.ENTERPRISE.value:
            return {"message": "已完成企业实名认证，无需重复认证"}
        elif "personal" in st:
            return {"message": "已完成个人实名认证，暂不支持再次企业认证"}

    # 验证手机号格式
    contact_phone = contact_phone.strip()
    if not re.fullmatch(r"1[3-9]\d{9}", contact_phone):
        raise HTTPException(status_code=400, detail="联系手机号格式不正确")

    # 验证手机验证码
    vc = db.query(VerificationCode).filter(
        VerificationCode.target == contact_phone,
        VerificationCode.code == phone_code,
        VerificationCode.type == 'sms',
        VerificationCode.created_at > datetime.utcnow() - timedelta(minutes=10)
    ).order_by(VerificationCode.created_at.desc()).first()

    if not vc:
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    # 统一社会信用代码格式验证（18位）
    license_no = license_no.strip().upper()
    if not re.match(r'^[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}$', license_no):
        raise HTTPException(status_code=400, detail="统一社会信用代码格式不正确")

    # 检查是否已有企业认证记录
    existing_profile = db.query(EnterpriseProfile).filter(EnterpriseProfile.user_id == user.id).first()
    if existing_profile and existing_profile.status == VerificationStatus.APPROVED:
        raise HTTPException(status_code=400, detail="已完成企业实名认证，无需重复认证")

    # 统一使用 /data/aiops/static/uploads，确保静态可访问
    upload_dir = "/data/aiops/static/uploads"
    os.makedirs(upload_dir, exist_ok=True)

    safe_name = os.path.basename(file.filename or 'license')
    file_path = os.path.join(upload_dir, f"license_{user.id}_{int(datetime.utcnow().timestamp())}_{safe_name}")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    license_image_url = f"/static/uploads/{os.path.basename(file_path)}"

    # 创建或更新企业认证记录
    if existing_profile:
        # 更新现有记录
        existing_profile.company_name = company_name
        existing_profile.license_no = license_no
        existing_profile.license_image_url = license_image_url
        existing_profile.contact_phone = contact_phone
        if wechat_id:
            existing_profile.wechat_id = wechat_id
        existing_profile.status = VerificationStatus.PENDING
        existing_profile.reviewer_id = None
        existing_profile.review_remark = None
        existing_profile.review_time = None
        existing_profile.updated_at = datetime.utcnow()
    else:
        # 创建新记录
        existing_profile = EnterpriseProfile(
            user_id=user.id,
            company_name=company_name,
            license_no=license_no,
            license_image_url=license_image_url,
            contact_phone=contact_phone,
            wechat_id=wechat_id,
            status=VerificationStatus.PENDING
        )
        db.add(existing_profile)

    # 更新用户状态为待审核
    user.business_license_url = license_image_url
    user.real_name_status = RealNameStatus.ENTERPRISE_PENDING
    user.user_type = "企业用户"
    if contact_phone and not user.phone:
        user.phone = contact_phone
    if wechat_id:
        user.wechat_id = wechat_id
        user.is_wechat_bound = True

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="认证提交失败，请稍后重试")

    return {"message": "企业认证信息已提交，等待管理员审核"}

@router.post("/user/change-password")
async def change_password(data: PasswordChangeSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(data.old_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="原密码错误")
    user.hashed_password = get_password_hash(data.new_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "密码修改成功"}

# --- 管理员审核API ---
def get_admin_user(user: User = Depends(get_current_user)):
    """检查是否为管理员"""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user

@router.get("/admin/enterprise/reviews")
async def list_enterprise_reviews(
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """获取企业认证审核列表"""
    query = db.query(EnterpriseProfile).join(User)
    
    if status:
        if status == "pending":
            query = query.filter(EnterpriseProfile.status == VerificationStatus.PENDING)
        elif status == "approved":
            query = query.filter(EnterpriseProfile.status == VerificationStatus.APPROVED)
        elif status == "rejected":
            query = query.filter(EnterpriseProfile.status == VerificationStatus.REJECTED)
    
    total = query.count()
    reviews = query.order_by(EnterpriseProfile.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    result = []
    for review in reviews:
        result.append({
            "id": review.id,
            "user_id": review.user_id,
            "username": review.user.username,
            "email": review.user.email,
            "company_name": review.company_name,
            "license_no": review.license_no,
            "license_image_url": review.license_image_url,
            "contact_phone": review.contact_phone,
            "wechat_id": review.wechat_id,
            "status": review.status.value,
            "reviewer_id": review.reviewer_id,
            "review_remark": review.review_remark,
            "review_time": review.review_time.isoformat() if review.review_time else None,
            "created_at": review.created_at.isoformat(),
            "updated_at": review.updated_at.isoformat()
        })
    
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "data": result
    }

@router.get("/admin/enterprise/reviews/{review_id}")
async def get_enterprise_review(
    review_id: int,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """获取企业认证详情"""
    review = db.query(EnterpriseProfile).filter(EnterpriseProfile.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="审核记录不存在")
    
    return {
        "id": review.id,
        "user_id": review.user_id,
        "username": review.user.username,
        "email": review.user.email,
        "company_name": review.company_name,
        "license_no": review.license_no,
        "license_image_url": review.license_image_url,
        "contact_phone": review.contact_phone,
        "wechat_id": review.wechat_id,
        "status": review.status.value,
        "reviewer_id": review.reviewer_id,
        "review_remark": review.review_remark,
        "review_time": review.review_time.isoformat() if review.review_time else None,
        "created_at": review.created_at.isoformat(),
        "updated_at": review.updated_at.isoformat()
    }

@router.post("/admin/enterprise/reviews/{review_id}/approve")
async def approve_enterprise_review(
    review_id: int,
    remark: Optional[str] = None,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """审核通过企业认证"""
    review = db.query(EnterpriseProfile).filter(EnterpriseProfile.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="审核记录不存在")
    
    if review.status == VerificationStatus.APPROVED:
        raise HTTPException(status_code=400, detail="该认证已通过审核")
    
    review.status = VerificationStatus.APPROVED
    review.reviewer_id = admin.id
    review.review_remark = remark
    review.review_time = datetime.utcnow()
    
    # 更新用户状态
    user = review.user
    user.real_name_status = RealNameStatus.ENTERPRISE
    user.is_verified = True
    
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"审核失败：{str(e)}")
    
    return {"message": "企业认证审核通过"}


@router.post("/admin/enterprise/reviews/{review_id}/reject")

@router.get("/admin/ops/overview")
async def get_ops_overview(
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """运营看板数据概览"""
    from datetime import datetime, timedelta
    from sqlalchemy import func, case
    
    # 1. 用户统计
    total_users = db.query(User).count()
    personal_users = db.query(User).filter(
        User.real_name_status.in_([RealNameStatus.PERSONAL, RealNameStatus.PERSONAL_PENDING])
    ).count()
    enterprise_users = db.query(User).filter(
        User.real_name_status.in_([RealNameStatus.ENTERPRISE, RealNameStatus.ENTERPRISE_PENDING])
    ).count()
    
    # 2. 今日注册数
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_registrations = db.query(User).filter(User.created_at >= today_start).count()
    
    # 3. 营收统计（只统计用户实际充值金额，不包含消费和免费赠送）
    today_revenue = db.query(func.sum(UsageLog.cost)).filter(
        UsageLog.timestamp >= today_start,
        UsageLog.cost > 0,
        UsageLog.task.like('充值%'),
    ).scalar() or 0.0
    
    week_start = today_start - timedelta(days=7)
    week_revenue = db.query(func.sum(UsageLog.cost)).filter(
        UsageLog.timestamp >= week_start,
        UsageLog.cost > 0,
        UsageLog.task.like('充值%'),
    ).scalar() or 0.0
    
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_revenue = db.query(func.sum(UsageLog.cost)).filter(
        UsageLog.timestamp >= month_start,
        UsageLog.cost > 0,
        UsageLog.task.like('充值%'),
    ).scalar() or 0.0
    
    # 4. 注册趋势（最近30天）
    trend_start = today_start - timedelta(days=30)
    daily_regs = db.query(
        func.date(User.created_at).label('date'),
        func.count(User.id).label('count')
    ).filter(
        User.created_at >= trend_start
    ).group_by(func.date(User.created_at)).all()
    
    # 构建趋势数据（填充缺失的日期为0）
    registration_trend = [0] * 30
    for reg in daily_regs:
        days_ago = (today_start.date() - reg.date).days
        if 0 <= days_ago < 30:
            registration_trend[29 - days_ago] = reg.count
    
    # 5. 营收趋势（最近30天，只统计实际充值金额）
    daily_revenue = db.query(
        func.date(UsageLog.timestamp).label('date'),
        func.sum(UsageLog.cost).label('revenue')
    ).filter(
        UsageLog.timestamp >= trend_start,
        UsageLog.cost > 0,
        UsageLog.task.like('充值%'),
    ).group_by(func.date(UsageLog.timestamp)).all()
    
    revenue_trend = [0.0] * 30
    for rev in daily_revenue:
        days_ago = (today_start.date() - rev.date).days
        if 0 <= days_ago < 30:
            revenue_trend[29 - days_ago] = float(rev.revenue or 0)
    
    return {
        "total_users": total_users,
        "personal_users": personal_users,
        "enterprise_users": enterprise_users,
        "today_registrations": today_registrations,
        "today_revenue": round(today_revenue, 2),
        "week_revenue": round(week_revenue, 2),
        "month_revenue": round(month_revenue, 2),
        "registration_trend": registration_trend,
        "revenue_trend": revenue_trend
    }

async def reject_enterprise_review(
    review_id: int,
    remark: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """审核拒绝企业认证"""
    if not remark or not remark.strip():
        raise HTTPException(status_code=400, detail="拒绝原因不能为空")
    
    review = db.query(EnterpriseProfile).filter(EnterpriseProfile.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="审核记录不存在")
    
    if review.status == VerificationStatus.REJECTED:
        raise HTTPException(status_code=400, detail="该认证已被拒绝")
    
    review.status = VerificationStatus.REJECTED
    review.reviewer_id = admin.id
    review.review_remark = remark.strip()
    review.review_time = datetime.utcnow()
    
    # 更新用户状态为待审核（允许重新提交）
    user = review.user
    user.real_name_status = RealNameStatus.ENTERPRISE_PENDING
    
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"审核失败：{str(e)}")
    
    return {"message": "企业认证审核已拒绝"}

@router.post("/user/bind-wechat")
async def bind_wechat(wechat_id: str, force: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wechat_id = (wechat_id or '').strip()
    if not wechat_id:
        raise HTTPException(status_code=400, detail="wechat_id 不能为空")

    # 已绑定：默认不允许重复绑定；force=true 允许更换
    if user.is_wechat_bound and user.wechat_id and not force:
        return {"message": "微信已绑定，无需重复绑定"}

    # wechat_id 唯一
    exists = db.query(User).filter(User.wechat_id == wechat_id, User.id != user.id).first()
    if exists:
        raise HTTPException(status_code=400, detail="该微信已被其他账号绑定")

    user.wechat_id = wechat_id
    user.is_wechat_bound = True

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="该微信已被其他账号绑定")

    return {"message": "微信绑定成功" if not force else "微信已更新绑定"}



@router.post("/user/bind-phone")
async def bind_phone(phone: str, code: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """绑定手机号（不改变实名认证状态）。

    - 校验短信验证码（10 分钟有效）
    - 手机号唯一（不能被其他账号占用）
    """
    phone = (phone or '').strip()
    code = (code or '').strip()
    if not re.fullmatch(r"1[3-9]\d{9}", phone):
        raise HTTPException(status_code=400, detail="手机号格式不正确")
    if not code:
        raise HTTPException(status_code=400, detail="验证码不能为空")

    # 手机号不可被其他账号占用
    exists = db.query(User).filter(User.phone == phone, User.id != user.id).first()
    if exists:
        raise HTTPException(status_code=400, detail="该手机号已被其他账号绑定")

    vc = db.query(VerificationCode).filter(
        VerificationCode.target == phone,
        VerificationCode.code == code,
        VerificationCode.type == 'sms',
        VerificationCode.created_at > datetime.utcnow() - timedelta(minutes=10)
    ).order_by(VerificationCode.created_at.desc()).first()

    if not vc:
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    user.phone = phone
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="该手机号已被其他账号绑定")

    return {"message": "手机号绑定成功"}
# --- Dashboard Stats ---
@router.get("/dashboard/stats")
async def get_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    host_count = db.query(SSHHost).filter(SSHHost.owner_id == user.id).count()
    usage_count = db.query(UsageLog).filter(UsageLog.user_id == user.id).count()
    kb_count = db.query(PrivateKB).filter(PrivateKB.owner_id == user.id).count()
    return {
        "host_count": host_count,
        "usage_count": usage_count,
        "kb_count": kb_count,
        "balance": round(user.balance, 2),
        "business_license_url": user.business_license_url
    }

# --- SSH 管理 ---
@router.post("/ssh/test")
async def test_ssh(host: SSHHostSchema, user: User = Depends(get_current_user)):
    return ssh_service.test_connection(host.dict())

@router.post("/ssh/hosts")
async def add_ssh_host(host: SSHHostSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    new_host = SSHHost(**host.dict(), owner_id=user.id)
    db.add(new_host)
    db.commit()
    return {"message": "主机已添加"}

@router.get("/ssh/hosts")
async def list_ssh_hosts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    hosts = db.query(SSHHost).filter(SSHHost.owner_id == user.id).all()
    return [{"id": h.id, "ip": h.ip, "port": h.port, "name": h.name, "username": h.username} for h in hosts]

@router.delete("/ssh/hosts/{host_id}")
async def delete_ssh_host(host_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    host = db.query(SSHHost).filter(SSHHost.id == host_id, SSHHost.owner_id == user.id).first()
    if not host: raise HTTPException(status_code=404)
    db.delete(host)
    db.commit()
    return {"message": "已删除"}

# --- 知识库 ---
@router.post("/kb/private")
async def add_private_kb(item: KBItemSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    new_item = PrivateKB(owner_id=user.id, title=item.title, content=item.content)
    db.add(new_item)
    db.commit()
    return {"message": "已保存到私有知识库"}

@router.get("/kb/private")
async def list_private_kb(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(PrivateKB).filter(PrivateKB.owner_id == user.id).all()
    return items

@router.delete("/kb/private/{item_id}")
async def delete_private_kb(item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(PrivateKB).filter(PrivateKB.id == item_id, PrivateKB.owner_id == user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="知识不存在")
    db.delete(item)
    db.commit()
    return {"message": "知识已删除"}

@router.get("/kb/public")
async def search_public_kb(url: str):
    try:
        res = requests.get(url, timeout=10)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, 'html.parser')
        title = soup.title.string if soup.title else url
        for script in soup(["script", "style"]):
            script.decompose()
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)[:500] + "..."
        return {"title": title, "content": text}
    except Exception as e:
        return {"title": "抓取失败", "content": str(e)}

# --- 会话管理 ---
@router.post("/chat/sessions")
async def save_session(sess: SessionSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    new_sess = ChatSession(user_id=user.id, title=sess.title, content=sess.content)
    db.add(new_sess)
    db.commit()
    return {"message": "会话已保存"}

@router.get("/chat/sessions")
async def list_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(ChatSession).filter(ChatSession.user_id == user.id).all()

# --- 计费与用量 ---
@router.get("/usage/balance")
async def get_balance(user: User = Depends(get_current_user)):
    return {
        "balance": round(user.balance, 2),
        "username": user.username,
        "user_type": user.user_type,
        "is_verified": user.is_verified,
        "created_at": user.created_at.strftime("%Y-%m-%d")
    }

@router.get("/usage/history")
async def get_usage_history(
    page: int = 1,
    page_size: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取用量明细，支持分页"""
    from sqlalchemy import func
    
    # 计算总数
    total = db.query(UsageLog).filter(UsageLog.user_id == user.id).count()
    
    # 分页查询
    offset = (page - 1) * page_size
    logs = db.query(UsageLog).filter(
        UsageLog.user_id == user.id
    ).order_by(UsageLog.timestamp.desc()).offset(offset).limit(page_size).all()
    
    return {
        "items": [{"date": l.timestamp.strftime("%Y-%m-%d %H:%M"), "task": mask_sensitive_info(l.task), "cost": l.cost} for l in logs],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 1
    }



@router.get("/usage/series")
async def get_usage_series(month: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """按月返回按天聚合的用量序列（用于图表）：
    - task_count: 任务调用次数（排除充值流水）
    - cost_sum: 消耗金额（排除充值流水）
    - tokens_sum: 消耗 tokens（排除充值流水）

    month 格式：YYYY-MM；为空则默认当前月（UTC）。
    """
    from datetime import datetime, date
    from calendar import monthrange

    # 1) 解析月份
    if month:
        try:
            y, m = month.split('-')
            year = int(y)
            mon = int(m)
            if mon < 1 or mon > 12:
                raise ValueError('invalid month')
            start = datetime(year, mon, 1)
        except Exception:
            raise HTTPException(status_code=400, detail='month 格式应为 YYYY-MM')
    else:
        now = datetime.utcnow()
        start = datetime(now.year, now.month, 1)

    # 2) 计算下月起始（作为 end）
    if start.month == 12:
        end = datetime(start.year + 1, 1, 1)
    else:
        end = datetime(start.year, start.month + 1, 1)

    # 3) 聚合查询（排除充值流水，避免把“入账金额”当成算力消耗）
    dcol = func.date(UsageLog.timestamp)
    q = (
        db.query(
            dcol.label('d'),
            func.count(UsageLog.id).label('task_count'),
            func.coalesce(func.sum(UsageLog.cost), 0.0).label('cost_sum'),
            func.coalesce(func.sum(UsageLog.tokens), 0).label('tokens_sum'),
        )
        .filter(
            UsageLog.user_id == user.id,
            UsageLog.timestamp >= start,
            UsageLog.timestamp < end,
            ~UsageLog.task.like('充值%'),
        )
        .group_by(dcol)
        .order_by(dcol.asc())
    )
    rows = q.all()

    def _dkey(v):
        # SQLite/MySQL 可能返回 date 或 str
        try:
            return v.isoformat()  # type: ignore[attr-defined]
        except Exception:
            return str(v)

    by_day = { _dkey(r.d): r for r in rows }

    # 4) 补齐整月日期（前端图表需要连续刻度）
    days = monthrange(start.year, start.month)[1]
    labels = []
    task_counts = []
    cost_sums = []
    tokens_sums = []

    for day in range(1, days + 1):
        d = date(start.year, start.month, day).isoformat()
        labels.append(d)
        r = by_day.get(d)
        task_counts.append(int(getattr(r, 'task_count', 0) or 0) if r else 0)
        cost_sums.append(float(getattr(r, 'cost_sum', 0.0) or 0.0) if r else 0.0)
        tokens_sums.append(int(getattr(r, 'tokens_sum', 0) or 0) if r else 0)

    return {
        'month': start.strftime('%Y-%m'),
        'labels': labels,
        'task_counts': task_counts,
        'cost_sums': cost_sums,
        'tokens_sums': tokens_sums,
        'total_task_count': sum(task_counts),
        'total_cost_sum': round(sum(cost_sums), 6),
        'total_tokens_sum': sum(tokens_sums),
    }

ALLOW_DEMO_RECHARGE = os.getenv("ALLOW_DEMO_RECHARGE", "false").lower() == "true"

def _gen_order_no():
    return datetime.utcnow().strftime("%Y%m%d%H%M%S") + ''.join(random.choices(string.digits, k=6))

def _mark_order_paid(order: PaymentOrder, db: Session, trade_no: str, raw: dict | None = None):
    """统一的成功入账逻辑，避免重复扣/加余额。"""
    if order.status == PaymentStatus.SUCCESS:
        return
    order.status = PaymentStatus.SUCCESS
    order.provider_trade_no = trade_no
    order.updated_at = datetime.utcnow()
    if raw:
        try:
            order.notify_payload = json.dumps(raw, ensure_ascii=False)
        except Exception:
            order.notify_payload = str(raw)
    user = db.query(User).filter(User.id == order.user_id).first()
    if user:
        user.balance += order.amount
        log = UsageLog(user_id=user.id, task=f"充值: {order.method.value}", cost=order.amount)
        db.add(log)
    db.commit()

@router.post("/usage/recharge")
async def recharge(amount: float, method: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """旧版演示充值接口，默认关闭，避免绕过真实支付流程。"""
    if not ALLOW_DEMO_RECHARGE:
        raise HTTPException(status_code=400, detail="请使用新的充值接口 /api/v1/usage/recharge/order")
    user.balance += amount
    log = UsageLog(user_id=user.id, task=f"充值(演示): {method}", cost=amount)
    db.add(log)
    db.commit()
    return {"message": f"成功充值 ￥{amount}"}

@router.post("/usage/recharge/order")
async def create_recharge_order(req: RechargeOrderSchema, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    amount = round(req.amount, 2)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="充值金额必须大于 0")
    method = (req.method or "").lower()
    if method not in ("wechat", "alipay"):
        raise HTTPException(status_code=400, detail="支付方式仅支持 wechat / alipay")

    out_trade_no = _gen_order_no()
    pay_method = PaymentMethod.WECHAT if method == "wechat" else PaymentMethod.ALIPAY
    order = PaymentOrder(
        out_trade_no=out_trade_no,
        user_id=user.id,
        amount=amount,
        method=pay_method,
        status=PaymentStatus.PENDING,
        description="账户充值",
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    base_url = str(request.base_url).rstrip("/")
    default_return = req.return_url or f"{base_url}/static/index.html"

    try:
        if method == "wechat":
            code_url = payment_service.create_wechat_native(out_trade_no, amount, "账户充值")
            order.request_payload = code_url
            db.commit()
            return {"order_no": out_trade_no, "method": method, "code_url": code_url}
        else:
            pay_url = payment_service.create_alipay_page(out_trade_no, amount, "账户充值", return_url=default_return)
            order.request_payload = pay_url
            db.commit()
            return {"order_no": out_trade_no, "method": method, "pay_url": pay_url}
    except ValueError as exc:
        db.delete(order)
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("创建支付订单失败: %s", exc)
        db.delete(order)
        db.commit()
        raise HTTPException(status_code=500, detail="支付下单失败，请检查支付配置")

@router.get("/usage/recharge/order/{order_no}")
async def query_recharge_order(order_no: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(PaymentOrder).filter(
        PaymentOrder.out_trade_no == order_no,
        PaymentOrder.user_id == user.id
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    return {
        "order_no": order.out_trade_no,
        "method": order.method.value,
        "amount": order.amount,
        "status": order.status.value,
        "provider_trade_no": order.provider_trade_no,
        "updated_at": order.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.post("/usage/recharge/order/{order_no}/sync")
async def sync_recharge_order(order_no: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Sync order status by querying provider (for callback delay/loss).

    - Only the order owner can sync; admin can sync any order.
    - Currently supports WeChat only.
    """
    q = db.query(PaymentOrder).filter(PaymentOrder.out_trade_no == order_no)
    order = q.filter(PaymentOrder.user_id == user.id).first()
    if not order and getattr(user, "is_admin", False):
        order = q.first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status == PaymentStatus.SUCCESS:
        return {
            "order_no": order.out_trade_no,
            "method": order.method.value,
            "amount": order.amount,
            "status": order.status.value,
            "provider_trade_no": order.provider_trade_no,
            "updated_at": order.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        }

    if order.method != PaymentMethod.WECHAT:
        raise HTTPException(status_code=400, detail="Only WeChat supports sync for now")

    client = getattr(payment_service, "wechat_client", None)
    if not client:
        raise HTTPException(status_code=400, detail="WeChat payment not configured")

    try:
        code, msg = client.query(out_trade_no=order.out_trade_no)
    except Exception as exc:
        logger.exception("WeChat query failed: %s", exc)
        raise HTTPException(status_code=400, detail="WeChat query failed")

    if code != 200:
        detail = msg if isinstance(msg, str) else str(msg)
        raise HTTPException(status_code=400, detail=f"WeChat query failed: {detail[:200]}")

    try:
        data = json.loads(msg) if isinstance(msg, str) else msg
    except Exception:
        data = {}

    trade_state = (data.get("trade_state") or "").upper()
    transaction_id = data.get("transaction_id") or ""

    if trade_state == "SUCCESS":
        _mark_order_paid(order, db, transaction_id)
    elif trade_state in ("CLOSED", "REVOKED", "PAYERROR"):
        order.status = PaymentStatus.FAILED
        order.notify_payload = json.dumps(data, ensure_ascii=False)
        order.updated_at = datetime.utcnow()
        db.commit()

    return {
        "order_no": order.out_trade_no,
        "method": order.method.value,
        "amount": order.amount,
        "status": order.status.value,
        "trade_state": trade_state,
        "provider_trade_no": order.provider_trade_no,
        "updated_at": order.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
    }

@router.post("/payment/notify/wechat")
async def wechat_notify(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    # 直接使用 Starlette Headers（大小写不敏感），避免转成 dict 后 header key 大小写敏感导致验签取不到 wechatpay-signature-type
    headers = request.headers
    try:
        notify_data = payment_service.parse_wechat_notify(headers=headers, body=body)
    except Exception as exc:
        logger.exception("微信支付回调验签失败: %s", exc)
        return JSONResponse(status_code=400, content={"code": "FAIL", "message": str(exc)})


    # wechatpayv3 在验签失败时可能返回 False/None；此处统一按回调验签失败处理，避免抛 500
    if not notify_data:
        return JSONResponse(status_code=400, content={"code": "FAIL", "message": "回调验签失败"})
    resource = notify_data.get("resource") or notify_data
    out_trade_no = resource.get("out_trade_no")
    trade_state = (resource.get("trade_state") or "").upper()
    transaction_id = resource.get("transaction_id")

    if not out_trade_no:
        return JSONResponse(status_code=400, content={"code": "FAIL", "message": "缺少 out_trade_no"})

    order = db.query(PaymentOrder).filter(PaymentOrder.out_trade_no == out_trade_no).first()
    if not order:
        return JSONResponse(status_code=404, content={"code": "FAIL", "message": "订单不存在"})

    if trade_state == "SUCCESS":
        _mark_order_paid(order, db, transaction_id or "")
        return JSONResponse(content={"code": "SUCCESS", "message": "OK"})
    else:
        order.status = PaymentStatus.FAILED
        order.notify_payload = json.dumps(resource, ensure_ascii=False)
        order.updated_at = datetime.utcnow()
        db.commit()
        return JSONResponse(status_code=400, content={"code": "FAIL", "message": f"状态异常: {trade_state}"})

@router.post("/payment/notify/alipay")
async def alipay_notify(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    data = dict(form)
    signature = data.pop("sign", None)
    data.pop("sign_type", None)

    if not signature or not payment_service.verify_alipay_notify(data, signature):
        return PlainTextResponse("failure")

    out_trade_no = data.get("out_trade_no")
    trade_no = data.get("trade_no")
    trade_status = data.get("trade_status")

    if not out_trade_no:
        return PlainTextResponse("failure")

    order = db.query(PaymentOrder).filter(PaymentOrder.out_trade_no == out_trade_no).first()
    if not order:
        return PlainTextResponse("failure")

    if trade_status in ("TRADE_SUCCESS", "TRADE_FINISHED"):
        _mark_order_paid(order, db, trade_no or "", raw=data)
        return PlainTextResponse("success")

    order.status = PaymentStatus.FAILED
    order.notify_payload = json.dumps(data, ensure_ascii=False)
    order.updated_at = datetime.utcnow()
    db.commit()
    return PlainTextResponse("failure")

# --- 核心 AI 功能 ---
@router.post("/ask")
async def ask_question(
    question: str, 
    conversation_id: Optional[str] = None,
    mode: str = "qa",  # qa 或 code
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """
    增强的问答接口，支持多轮对话和精准理解
    """
    try:
        # 使用增强的RAG服务（支持多轮对话）
        result = enhanced_rag_service.query(
            question=question,
            user_id=user.id,
            conversation_id=conversation_id,
            mode=mode
        )
        # 免费问答/脚本咨询，不扣点，仅记录次数
        log = UsageLog(user_id=user.id, task=f"问答: {question[:40]}", cost=0.0)
        db.add(log); db.commit()
        return result
    except Exception as e: 
        logger.error(f"问答失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ssh/propose")
async def propose_ops(req: ProposeSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    增强的排障计划生成接口，支持对话上下文和更精确的命令生成
    """
    host = db.query(SSHHost).filter(SSHHost.id == req.host_id, SSHHost.owner_id == user.id).first()
    if not host: raise HTTPException(status_code=404)
    # 计费：排障计划消耗算力点
    if user.balance < TROUBLESHOOT_BASE_POINTS:
        raise HTTPException(
            status_code=402, 
            detail="您好，您的算力不足，请充值算力。方案咨询和代码编写永久免费，排障与部署扣算力点收费。"
        )
    user.balance -= TROUBLESHOOT_BASE_POINTS
    log = UsageLog(
        user_id=user.id,
        task=f"排障计划: {req.task[:60]}",
        cost=TROUBLESHOOT_BASE_POINTS,
    )
    db.add(log)
    db.commit()
    
    # 检查余额是否不足，给用户提示
    if user.balance < TROUBLESHOOT_BASE_POINTS:
        logger.info(f"用户 {user.id} 算力余额不足，当前余额: {user.balance}")
    # 使用增强的SSH服务（支持对话上下文和更精确的命令生成）
    plan = await enhanced_ssh_service.generate_plan(
        task_description=req.task,
        host_context=host.ip,
        user_id=user.id,
        conversation_id=req.conversation_id
    )
    
    # 确保plan是数组格式
    if not isinstance(plan, list):
        logger.error(f"plan不是数组格式: {type(plan)}, 内容: {plan}")
        plan = []
    
    # 验证plan中的每个步骤都有有效的cmd
    validated_plan = []
    for step in plan:
        if isinstance(step, dict) and step.get("cmd"):
            cmd = str(step.get("cmd", "")).strip()
            # 再次验证命令不是JSON片段
            if cmd and not cmd.startswith('"steps"') and not cmd.startswith('"cmd"') and not cmd.startswith('{'):
                validated_plan.append({
                    "desc": str(step.get("desc", "执行命令")).strip(),
                    "cmd": cmd
                })
    
    if not validated_plan:
        logger.warning(f"没有有效的命令步骤，原始plan: {plan}")
        raise HTTPException(status_code=500, detail="未能生成有效的执行计划，请重试或换个更具体的指令")
    
    return {
        "host_ip": host.ip, 
        "plan": validated_plan, 
        "deducted_points": TROUBLESHOOT_BASE_POINTS,
        "conversation_id": req.conversation_id  # 返回对话ID供前端使用
    }

@router.post("/ssh/execute")
async def execute_ops(req: ExecSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    host = db.query(SSHHost).filter(SSHHost.id == req.host_id, SSHHost.owner_id == user.id).first()
    if not host: raise HTTPException(status_code=404)
    res = await run_in_threadpool(ssh_service.execute_command, {
        "ip": host.ip, "port": host.port, "username": host.username, "password": host.password, "private_key": host.private_key
    }, req.command)
    # 执行阶段不重复扣点，仅记录
    log = UsageLog(user_id=user.id, task=f"执行: {req.command[:60]}", cost=0.0)
    db.add(log); db.commit()
    return res


@router.get("/admin/ops/users")
async def get_ops_users(
    page: int = 1,
    page_size: int = 20,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """运营看板用户列表"""
    offset = (page - 1) * page_size
    total = db.query(User).count()
    users = db.query(User).order_by(User.created_at.desc()).offset(offset).limit(page_size).all()
    
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [{
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "phone": u.phone,
            "balance": u.balance,
            "created_at": u.created_at.strftime("%Y-%m-%d %H:%M:%S") if u.created_at else "",
            "user_type": u.user_type,
            "tier": u.tier.value
        } for u in users]
    }


from fastapi import Request
from app.models.user import WebsiteVisit
from sqlalchemy import func

@router.post("/site/visits")
async def track_visits(request: Request, db: Session = Depends(get_db)):
    """Record a website visit"""
    # Get IP
    ip = request.headers.get("x-forwarded-for", request.client.host).split(",")[0].strip()
    
    # Get Metadata
    user_agent = request.headers.get("user-agent", "")
    referrer = request.headers.get("referer", "") # Note spelling in header
    
    # Simple Location (Mock or External API - Skipping external call to avoid latency/blocking)
    # In a real app, use GeoIP2 local DB or async task.
    # For now, we store IP. Frontend dashboard *could* resolve it or we just group by IP.
    
    visit = WebsiteVisit(
        ip=ip,
        user_agent=user_agent[:500],
        referrer=referrer[:500]
    )
    db.add(visit)
    db.commit()
    
    # Return total count for homepage counter
    count = db.query(WebsiteVisit).count()
    # Add offset to make it look good (legacy file had 1024)
    return {"count": count + 1024}

@router.get("/admin/ops/visits/stats")
async def get_visit_stats(
    days: int = 7,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Get traffic statistics for dashboard"""
    from datetime import datetime, timedelta
    
    now = datetime.utcnow()
    start_date = now - timedelta(days=days)
    
    # 1. Total & Today
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    total_visits = db.query(WebsiteVisit).count() + 1024
    today_visits = db.query(WebsiteVisit).filter(WebsiteVisit.timestamp >= today_start).count()
    
    # 2. Trend (Daily)
    trend_data = db.query(
        func.date(WebsiteVisit.timestamp).label('date'),
        func.count(WebsiteVisit.id).label('count')
    ).filter(
        WebsiteVisit.timestamp >= start_date
    ).group_by(func.date(WebsiteVisit.timestamp)).all()
    
    trend = {str(t.date): t.count for t in trend_data}
    
    # Fill missing days
    daily_trend = []
    labels = []
    for i in range(days):
        d = (start_date + timedelta(days=i)).date()
        d_str = str(d)
        daily_trend.append(trend.get(d_str, 0))
        labels.append(d.strftime("%m-%d"))
        
    # 3. Top Referrers
    # Simple parsing: extract domain from referrer
    # Since doing this in SQL is hard for full URLs, let's fetch recent ones or do simple grouping
    # Group by full referrer for now
    top_refs = db.query(
        WebsiteVisit.referrer,
        func.count(WebsiteVisit.id).label('count')
    ).filter(
        WebsiteVisit.timestamp >= start_date,
        WebsiteVisit.referrer != None,
        WebsiteVisit.referrer != ""
    ).group_by(WebsiteVisit.referrer).order_by(func.count(WebsiteVisit.id).desc()).limit(10).all()
    
    referrers = [{"name": r.referrer or "Direct", "value": r.count} for r in top_refs]
    
    # 4. Recent Visits (Log)
    recent = db.query(WebsiteVisit).order_by(WebsiteVisit.timestamp.desc()).limit(20).all()
    recent_logs = [{
        "ip": v.ip,
        "time": v.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "source": v.referrer or "Direct",
        "ua": v.user_agent
    } for v in recent]

    return {
        "total": total_visits,
        "today": today_visits,
        "trend": {"labels": labels, "data": daily_trend},
        "referrers": referrers,
        "recent": recent_logs
    }
