from sqlalchemy import create_engine, Column, Integer, String, Enum, Float, ForeignKey, DateTime, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import enum
from datetime import datetime
import os

import os
DATABASE_URL = os.getenv('DATABASE_URL', 'mysql+pymysql://root:123qweQWE,./@127.0.0.1:3306/aiops')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class UserTier(enum.Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"

class RealNameStatus(enum.Enum):
    NONE = "none"
    PERSONAL_PENDING = "personal_pending"  # 个人认证待审核
    PERSONAL = "personal"  # 个人认证已通过
    ENTERPRISE_PENDING = "enterprise_pending"  # 企业认证待审核
    ENTERPRISE = "enterprise"  # 企业认证已通过

class VerificationStatus(enum.Enum):
    PENDING = "pending"      # 待审核
    APPROVED = "approved"    # 已通过
    REJECTED = "rejected"    # 已拒绝

class PaymentMethod(enum.Enum):
    WECHAT = "wechat"
    ALIPAY = "alipay"

class PaymentStatus(enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    CLOSED = "closed"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True)
    email = Column(String(255), unique=True, index=True)
    phone = Column(String(255), unique=True, index=True, nullable=True)
    hashed_password = Column(String(255))
    tier = Column(Enum(UserTier), default=UserTier.FREE)
    balance = Column(Float, default=300.0)  # 新用户默认300个算力值
    total_tokens = Column(Integer, default=0)
    
    # 扩展字段
    created_at = Column(DateTime, default=datetime.utcnow)
    is_verified = Column(Boolean, default=False)
    real_name_status = Column(Enum(RealNameStatus), default=RealNameStatus.NONE)
    user_type = Column(String(255), default="个人用户") # 个人用户/企业用户
    
    # 绑定信息
    wechat_id = Column(String(255), unique=True, nullable=True)
    is_wechat_bound = Column(Boolean, default=False)
    business_license_url = Column(String(255), nullable=True)
    
    # 管理员权限
    is_admin = Column(Boolean, default=False)  # 是否为管理员
    
    hosts = relationship("SSHHost", back_populates="owner")
    logs = relationship("UsageLog", back_populates="user")
    sessions = relationship("ChatSession", back_populates="user")
    private_kb = relationship("PrivateKB", back_populates="owner")

class VerificationCode(Base):
    __tablename__ = "verification_codes"
    id = Column(Integer, primary_key=True, index=True)
    target = Column(String(255), index=True) # email or phone
    code = Column(String(255))
    type = Column(String(255)) # 'email' or 'sms'
    created_at = Column(DateTime, default=datetime.utcnow)

class SSHHost(Base):
    __tablename__ = "ssh_hosts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255))
    ip = Column(String(255))
    port = Column(Integer, default=22)
    username = Column(String(255))
    password = Column(String(255))
        # Auth & Source info
    auth_type = Column(String(50), default='password') # password, key
    private_key = Column(Text, nullable=True)
    source = Column(String(50), default='manual') # manual, tencent, huawei, jumpserver
    region = Column(String(50), nullable=True)
    instance_id = Column(String(100), nullable=True)
    
    owner_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="hosts")

class UsageLog(Base):
    __tablename__ = "usage_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    task = Column(String(255))
    tokens = Column(Integer)
    cost = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="logs")

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String(255))
    content = Column(Text) # JSON string of messages
    updated_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="sessions")

class PrivateKB(Base):
    __tablename__ = "private_kb"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String(255))
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("User", back_populates="private_kb")

class PaymentOrder(Base):
    __tablename__ = "payment_orders"
    id = Column(Integer, primary_key=True, index=True)
    out_trade_no = Column(String(64), unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    method = Column(Enum(PaymentMethod))
    amount = Column(Float)
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    provider_trade_no = Column(String(128), nullable=True)
    description = Column(String(255), default="账户充值")
    request_payload = Column(Text, nullable=True)
    notify_payload = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", backref="payment_orders")

class EnterpriseProfile(Base):
    __tablename__ = "enterprise_profiles"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True)
    
    # 企业基本信息
    company_name = Column(String(255), nullable=False)  # 企业名称
    license_no = Column(String(100), nullable=False)    # 统一社会信用代码（证件号码）
    license_image_url = Column(String(500), nullable=False)  # 营业执照照片URL
    
    # 联系信息
    contact_phone = Column(String(20), nullable=False)  # 联系手机号
    wechat_id = Column(String(255), nullable=True)      # 企业微信ID（可选）
    
    # 审核状态
    status = Column(Enum(VerificationStatus), default=VerificationStatus.PENDING)
    
    # 审核信息
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # 审核管理员ID
    review_remark = Column(Text, nullable=True)  # 审核备注
    review_time = Column(DateTime, nullable=True)  # 审核时间
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联关系
    user = relationship("User", foreign_keys=[user_id], backref="enterprise_profile")
    reviewer = relationship("User", foreign_keys=[reviewer_id])

def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    from app.core.auth import get_password_hash
    if not db.query(User).filter(User.username == "admin").first():
        admin = User(
            username="admin",
            email="admin@opsgpt.com",
            hashed_password=get_password_hash("admin@123A"),
            tier=UserTier.ENTERPRISE,
            balance=99.0,
            user_type="企业用户",
            is_verified=True,
            real_name_status=RealNameStatus.ENTERPRISE,
            is_admin=True  # 设置为管理员
        )
        db.add(admin)
        db.commit()
    db.close()

class WebsiteVisit(Base):
    __tablename__ = "website_visits"
    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String(50), index=True)
    country = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)
    referrer = Column(String(500), nullable=True)
    user_agent = Column(String(500), nullable=True)
    path = Column(String(255), default="/")
    timestamp = Column(DateTime, default=datetime.utcnow)
