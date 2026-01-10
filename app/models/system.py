from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

# 复用现有的 SQLAlchemy Base / engine / SessionLocal
# 注意：必须在 init_db() 调用 Base.metadata.create_all 之前 import 本模块，
# 才能确保表被创建。
from app.models.user import Base  # noqa: F401


class SystemSetting(Base):
    """系统级键值配置（纯离线私有化部署）。"""

    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(255), unique=True, index=True, nullable=False)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class LicenseState(Base):
    """机器码绑定 + 试用期 + license token（约定单行 id=1）。"""

    __tablename__ = "license_state"

    id = Column(Integer, primary_key=True, index=True)
    machine_code = Column(String(128), nullable=False)

    trial_start = Column(DateTime, nullable=True)
    trial_end = Column(DateTime, nullable=True)

    license_token = Column(Text, nullable=True)
    license_expiry = Column(DateTime, nullable=True)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
