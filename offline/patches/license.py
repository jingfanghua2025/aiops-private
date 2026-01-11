import base64
import hashlib
import json
import os
from datetime import datetime, timedelta
from typing import Any, Tuple

from fastapi.responses import JSONResponse
from jose import jwt
from sqlalchemy.orm import Session

from app.models.user import SessionLocal
from app.models.system import LicenseState, SystemSetting


TRIAL_DAYS = int(os.getenv("LICENSE_TRIAL_DAYS", "30"))


def is_request_exempt(path: str) -> bool:
    """
    免授权校验的路径：
    - 健康检查 / 静态资源
    - 登录/注册等认证接口
    - License状态/激活接口（用于到期后申请并录入license）
    """
    if path == "/health" or path.startswith("/static/") or path == "/":
        return True
    if path.startswith("/api/v1/auth/"):
        return True
    if path.startswith("/api/v1/system/license/"):
        return True
    if path == "/api/v1/system/public":
        return True
    return False


def _read_text(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return None


def get_machine_fingerprint() -> str:
    """
    机器码：取多个稳定信息拼接后 sha256。
    目标：离线可用、重启不变、尽量与硬件绑定。
    """
    # 优先使用安装器写入的机器码（宿主机计算），保证 Docker 场景下重建容器不变
    env_mc = (os.getenv("AIOPS_MACHINE_CODE") or "").strip()
    if env_mc:
        return env_mc

    # Docker 场景可挂载宿主机信息到 /host/*

    parts: list[str] = []
    machine_id = _read_text("/host/etc/machine-id") or _read_text("/etc/machine-id")
    if machine_id:
        parts.append(f"machine-id:{machine_id}")

    product_uuid = _read_text("/host/sys/class/dmi/id/product_uuid") or _read_text("/sys/class/dmi/id/product_uuid")
    if product_uuid:
        parts.append(f"product-uuid:{product_uuid}")

    # MAC 地址（过滤 lo 与明显的虚拟接口）
    try:
        net_root = "/host/sys/class/net" if os.path.isdir("/host/sys/class/net") else "/sys/class/net"
        for nic in sorted(os.listdir(net_root)):
            if nic in ("lo",):
                continue
            addr = _read_text(f"{net_root}/{nic}/address")
            if not addr:
                continue
            if addr.lower() in ("00:00:00:00:00:00",):
                continue
            parts.append(f"mac:{nic}:{addr.lower()}")
    except Exception:
        pass

    raw = "|".join(parts) if parts else "unknown"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()
    # 展示用：保留前32位更短；内部仍可用全量
    return digest


def _now() -> datetime:
    # 使用 naive UTC，避免数据库层丢失 tzinfo 导致比较异常
    return datetime.utcnow()


def _get_setting(db: Session, key: str) -> str | None:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not row:
        return None
    return row.value


def _load_license_public_key() -> str | None:
    # 优先 env 指定，其次默认路径
    path = os.getenv("LICENSE_PUBLIC_KEY_PATH") or "/data/aiops/keys/license_public.pem"
    if os.path.exists(path):
        return _read_text(path)
    return None


def _verify_license_token(token: str, machine_code: str) -> Tuple[bool, dict[str, Any] | None, str | None]:
    pub = _load_license_public_key()
    if not pub:
        return False, None, "未配置 LICENSE_PUBLIC_KEY_PATH / license_public.pem"
    try:
        payload = jwt.decode(token, pub, algorithms=["RS256"])
    except Exception as exc:
        return False, None, f"license验签失败: {exc}"
    # 绑定机器码
    if payload.get("machine_code") != machine_code:
        return False, None, "license与本机机器码不匹配"
    return True, payload, None


def ensure_license_state() -> Tuple[bool, dict[str, Any]]:
    """
    返回 (ok, detail)
    - ok=True：允许访问
    - ok=False：需要激活license
    """
    db = SessionLocal()
    try:
        machine_code = get_machine_fingerprint()
        st = db.query(LicenseState).filter(LicenseState.id == 1).first()
        if not st:
            # 首次启动：创建试用期
            start = _now()
            end = start + timedelta(days=TRIAL_DAYS)
            st = LicenseState(
                id=1,
                machine_code=machine_code,
                trial_start=start,
                trial_end=end,
                license_token=None,
                license_expiry=None,
                updated_at=start,
            )
            db.add(st)
            db.commit()
            return True, {
                "mode": "trial",
                "machine_code": machine_code,
                "trial_end": st.trial_end.isoformat(),
            }

        # 机器码变化：直接视为未授权（防拷贝）
        if st.machine_code != machine_code:
            # 若尚未激活 license（仅试用），允许重新绑定机器码（Docker 容器重建/升级等场景）
            if not st.license_token:
                st.machine_code = machine_code
                st.updated_at = _now()
                db.commit()
            else:
                return False, {
                    "reason": "machine_code_changed",
                    "machine_code": machine_code,
                    "message": "机器码已变化，请重新申请license",
                }

        # 有license则优先校验license
        if st.license_token:
            ok, payload, err = _verify_license_token(st.license_token, machine_code)
            if ok and payload:
                # exp 由 jose 自动校验；这里取展示
                exp = payload.get("exp")
                exp_iso = None
                if isinstance(exp, (int, float)):
                    exp_iso = datetime.utcfromtimestamp(exp).isoformat()
                return True, {"mode": "license", "machine_code": machine_code, "license_expiry": exp_iso}
            return False, {
                "reason": "license_invalid",
                "machine_code": machine_code,
                "message": err or "license无效",
            }

        # 无license：检查试用期
        now = _now()
        if st.trial_end and now <= st.trial_end:
            return True, {
                "mode": "trial",
                "machine_code": machine_code,
                "trial_end": st.trial_end.isoformat(),
            }
        return False, {
            "reason": "trial_expired",
            "machine_code": machine_code,
            "trial_end": st.trial_end.isoformat() if st.trial_end else None,
            "message": "试用期已到期，请申请license激活",
        }
    finally:
        db.close()


def activate_license(token: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        machine_code = get_machine_fingerprint()
        ok, payload, err = _verify_license_token(token, machine_code)
        if not ok or not payload:
            raise ValueError(err or "license无效")

        st = db.query(LicenseState).filter(LicenseState.id == 1).first()
        if not st:
            st = LicenseState(id=1, machine_code=machine_code)
            db.add(st)

        exp = payload.get("exp")
        exp_dt = None
        if isinstance(exp, (int, float)):
            exp_dt = datetime.utcfromtimestamp(exp)

        st.machine_code = machine_code
        st.license_token = token
        st.license_expiry = exp_dt
        st.updated_at = _now()
        db.commit()
        return {
            "message": "license激活成功",
            "machine_code": machine_code,
            "license_expiry": exp_dt.isoformat() if exp_dt else None,
        }
    finally:
        db.close()


def license_block_response(detail: dict[str, Any]) -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={
            "detail": "需要license激活",
            "license": detail,
        },
    )

