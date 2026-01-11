from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi import UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session
from jose import jwt

from app.core.auth import oauth2_scheme, SECRET_KEY, ALGORITHM
from app.core.license import ensure_license_state, activate_license, get_machine_fingerprint
from app.models.user import SessionLocal, User, UserTier, RealNameStatus
from app.models.system import SystemSetting
from app.services.ai_service import reset_ai_service

router = APIRouter()

PRIVATE_DEPLOYMENT = os.getenv("PRIVATE_DEPLOYMENT", "false").lower() in ("1","true","yes","y")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="未登录")
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(status_code=401, detail="未登录")
        return user
    except Exception:
        raise HTTPException(status_code=401, detail="未登录")


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    return user


class ActivateReq(BaseModel):
    token: str


def _license_public_key_path() -> str:
    # 与 app.core.license._load_license_public_key 保持一致：优先 env，其次默认路径
    return os.getenv("LICENSE_PUBLIC_KEY_PATH") or "/data/aiops/keys/license_public.pem"


class SettingItem(BaseModel):
    key: str
    value: str | None = None


class SettingsUpsertReq(BaseModel):
    items: list[SettingItem]


def _mask_secret(val: str | None) -> str | None:
    if not val:
        return val
    if len(val) <= 8:
        return "****"
    return val[:2] + "****" + val[-2:]

# ---- Public info (no auth) ----
@router.get("/public")
def public_info() -> dict[str, Any]:
    ok, detail = ensure_license_state()
    return {
        "private_deployment": PRIVATE_DEPLOYMENT,
        "license_ok": ok,
        "license_detail": detail,
        "login_hint": {
            "ports": [80, 8000],
            "path": "/",
            "auth": "username_password_only" if PRIVATE_DEPLOYMENT else "multi",
        },
    }




@router.get("/license/status")
def license_status(_: User = Depends(require_admin)) -> dict[str, Any]:
    ok, detail = ensure_license_state()
    return {"ok": ok, "detail": detail}


@router.get("/license/machine-code")
def license_machine_code(_: User = Depends(require_admin)) -> dict[str, Any]:
    return {"machine_code": get_machine_fingerprint()}

@router.get("/license/request")
def license_request(months: int = 1, _: User = Depends(require_admin)) -> dict[str, Any]:
    """生成离线 license 申请信息（用于在官网提交机器码申请续期）。

    私有化环境通常无法出网：请把返回的 request_code 拷贝到可联网环境提交。
    """
    import base64, json
    months = int(months or 1)
    if months not in (1, 3, 6, 12, 24, 36):
        raise HTTPException(status_code=400, detail="months仅支持: 1/3/6/12/24/36")
    machine_code = get_machine_fingerprint()
    ok, detail = ensure_license_state()
    payload = {
        "product": "跃云-AIOps",
        "machine_code": machine_code,
        "requested_months": months,
    }
    request_code = base64.urlsafe_b64encode(json.dumps(payload, ensure_ascii=False).encode('utf-8')).decode('utf-8')
    return {
        "license_ok": ok,
        "license_detail": detail,
        "machine_code": machine_code,
        "request_code": request_code,
        "steps": [
            "在本私有化系统中复制机器码/申请码",
            "到可联网环境访问跃云官网的 license 申请页面，提交申请码（含申请时长）",
            "等待审批后获取 license token",
            "回到本系统：系统设置 -> License 激活，粘贴 token 完成开通",
        ],
    }


@router.post("/license/token/import")
async def license_token_import(file: UploadFile = File(...), _: User = Depends(require_admin)) -> dict[str, Any]:
    """从文件导入 license token（避免手动粘贴）。"""
    raw = (await file.read()).decode("utf-8", errors="ignore")
    # 去除空白/换行/零宽字符，避免“复制粘贴换行”导致验签失败
    token = "".join(ch for ch in (raw or "") if ch.strip()).strip()
    if not token:
        raise HTTPException(status_code=400, detail="文件为空或未包含token")
    try:
        return activate_license(token)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/license/public-key/import")
async def license_public_key_import(file: UploadFile = File(...), _: User = Depends(require_admin)) -> dict[str, Any]:
    """导入 license 公钥（PEM），用于离线环境验签 license token。"""
    raw = (await file.read()).decode("utf-8", errors="ignore").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="文件为空")
    if "BEGIN PUBLIC KEY" not in raw:
        raise HTTPException(status_code=400, detail="公钥格式不正确：请上传 PEM 公钥（BEGIN PUBLIC KEY）")

    # 校验 PEM 合法性（避免写入错误文件导致激活失败）
    try:
        from cryptography.hazmat.primitives import serialization
        serialization.load_pem_public_key(raw.encode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"公钥解析失败：{exc}")

    path = _license_public_key_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(raw.strip() + "\n")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"写入公钥失败：{exc}")

    return {"message": "公钥导入成功", "path": path}



@router.post("/license/activate")
def license_activate(req: ActivateReq, _: User = Depends(require_admin)) -> dict[str, Any]:
    # 去除空白/换行/零宽字符，避免“复制粘贴换行”导致验签失败
    token = "".join(ch for ch in (req.token or "") if ch.strip()).strip()
    if not token:
        raise HTTPException(status_code=400, detail="token不能为空")
    try:
        return activate_license(token)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/settings")
def get_settings(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    keys = [
        # LLM
        "AI_MODEL_PROVIDER",
        "OPENAI_API_BASE",
        "OPENAI_API_KEY",
        "MODEL_NAME",
        "DASHSCOPE_API_BASE",
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_MODEL_NAME",
        # Repos
        "GITLAB_BASE_URL",
        "GITLAB_TOKEN",
        "IMAGE_REGISTRY",
        "NEXUS_BASE_URL",
        "NEXUS_USER",
        "NEXUS_PASS",
        # K8S
        "KUBECONFIG_YAML",
    ]

    rows = db.query(SystemSetting).filter(SystemSetting.key.in_(keys)).all()
    mp = {r.key: r.value for r in rows}

    # 对敏感字段脱敏
    resp = {}
    for k in keys:
        v = mp.get(k)
        if k in ("OPENAI_API_KEY", "DASHSCOPE_API_KEY", "GITLAB_TOKEN", "NEXUS_PASS"):
            resp[k] = _mask_secret(v)
            resp[f"{k}__present"] = bool(v)
        elif k == "KUBECONFIG_YAML":
            resp[k] = "***已保存***" if v else None
            resp[f"{k}__present"] = bool(v)
        else:
            resp[k] = v
    return resp


@router.post("/settings")
def upsert_settings(req: SettingsUpsertReq, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    if not req.items:
        raise HTTPException(status_code=400, detail="items不能为空")

    # 允许写入的 key 白名单
    allowed = {
        "AI_MODEL_PROVIDER",
        "OPENAI_API_BASE",
        "OPENAI_API_KEY",
        "MODEL_NAME",
        "DASHSCOPE_API_BASE",
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_MODEL_NAME",
        "GITLAB_BASE_URL",
        "GITLAB_TOKEN",
        "IMAGE_REGISTRY",
        "NEXUS_BASE_URL",
        "NEXUS_USER",
        "NEXUS_PASS",
        "KUBECONFIG_YAML",
    }

    changed_keys: set[str] = set()
    for it in req.items:
        k = (it.key or "").strip()
        if not k or k not in allowed:
            raise HTTPException(status_code=400, detail=f"不支持的key: {k}")
        v = it.value
        row = db.query(SystemSetting).filter(SystemSetting.key == k).first()
        if not row:
            row = SystemSetting(key=k, value=v)
            db.add(row)
        else:
            row.value = v
        changed_keys.add(k)

    db.commit()

    # LLM 配置变更后重置单例，确保生效
    if changed_keys & {
        "AI_MODEL_PROVIDER",
        "OPENAI_API_BASE",
        "OPENAI_API_KEY",
        "MODEL_NAME",
        "DASHSCOPE_API_BASE",
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_MODEL_NAME",
    }:
        reset_ai_service()

    return {"message": "保存成功", "changed": sorted(changed_keys)}


# ---- Admin user management (private deployment) ----
class CreateUserReq(BaseModel):
    username: str
    password: str
    is_admin: bool = False


class UpdateUserReq(BaseModel):
    username: str | None = None
    is_admin: bool | None = None


@router.get("/users")
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    users = db.query(User).order_by(User.id.asc()).all()
    return {
        "items": [
            {
                "id": u.id,
                "username": u.username,
                "is_admin": bool(getattr(u, 'is_admin', False)),
                "created_at": u.created_at.isoformat() if getattr(u, 'created_at', None) else None,
            }
            for u in users
        ]
    }


@router.post("/users")
def create_user(req: CreateUserReq, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    if not PRIVATE_DEPLOYMENT:
        raise HTTPException(status_code=404, detail="仅私有化部署启用")
    username = (req.username or '').strip()
    password = (req.password or '').strip()
    if not username or not password:
        raise HTTPException(status_code=400, detail="username/password不能为空")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")

    from app.core.auth import get_password_hash
    u = User(
        username=username,
        email=f"{username}@local",
        hashed_password=get_password_hash(password),
        tier=UserTier.ENTERPRISE,
        balance=0.0,
        user_type="私有化用户",
        is_verified=True,
        real_name_status=RealNameStatus.NONE,
        is_admin=bool(req.is_admin),
    )
    db.add(u)
    db.commit()
    return {"message": "创建成功", "id": u.id}


@router.put("/users/{user_id}")
def update_user(user_id: int, req: UpdateUserReq, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    if not PRIVATE_DEPLOYMENT:
        raise HTTPException(status_code=404, detail="仅私有化部署启用")
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    if req.username is not None:
        name = req.username.strip()
        if not name:
            raise HTTPException(status_code=400, detail="username不能为空")
        exists = db.query(User).filter(User.username == name, User.id != user_id).first()
        if exists:
            raise HTTPException(status_code=400, detail="用户名已存在")
        u.username = name
    if req.is_admin is not None:
        u.is_admin = bool(req.is_admin)
    db.commit()
    return {"message": "更新成功"}


class ResetPasswordReq(BaseModel):
    new_password: str


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, req: ResetPasswordReq, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    if not PRIVATE_DEPLOYMENT:
        raise HTTPException(status_code=404, detail="仅私有化部署启用")
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    from app.core.auth import get_password_hash
    pwd = (req.new_password or '').strip()
    if len(pwd) < 8:
        raise HTTPException(status_code=400, detail="新密码至少8位")
    u.hashed_password = get_password_hash(pwd)
    db.commit()
    return {"message": "重置成功"}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    if not PRIVATE_DEPLOYMENT:
        raise HTTPException(status_code=404, detail="仅私有化部署启用")
    if admin.id == user_id:
        raise HTTPException(status_code=400, detail="不能删除当前登录管理员")
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    db.delete(u)
    db.commit()
    return {"message": "删除成功"}
