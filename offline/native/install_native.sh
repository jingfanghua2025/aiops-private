#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OFFLINE_DIR="$(cd "$ROOT_DIR/.." && pwd)"
AIOPS_HOME="/opt/aiops"
VENV_DIR="$AIOPS_HOME/venv"
APP_DIR="$AIOPS_HOME/app"
ENV_FILE="$AIOPS_HOME/aiops.env"
LOG_DIR="$AIOPS_HOME/logs"

log(){ echo "[$(date +'%F %T')] $*"; }
die(){ echo "ERROR: $*" >&2; exit 1; }

require_root(){ [[ "$(id -u)" == "0" ]] || die "请使用 root 执行（或 sudo）"; }

os_detect(){
  if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    echo "${ID:-unknown}" "${VERSION_ID:-unknown}"
  else
    echo unknown unknown
  fi
}

install_system_deps(){
  read -r os_id os_ver < <(os_detect)
  log "OS: $os_id $os_ver"

  if [[ "$os_id" =~ (ubuntu|debian) ]]; then
    # 依赖：python3/venv/pip，nginx 可选
    apt-get update -y
    apt-get install -y python3 python3-venv python3-pip nginx || true
  elif [[ "$os_id" =~ (centos|rhel) && "$os_ver" =~ ^7 ]]; then
    yum install -y epel-release || true
    yum install -y python3 python3-venv python3-pip nginx || true
  elif [[ "$os_id" =~ (rocky|almalinux|rhel|centos) ]]; then
    dnf install -y python3 python3-pip nginx || true
    python3 -m ensurepip --upgrade >/dev/null 2>&1 || true
  else
    die "不支持的系统：$os_id $os_ver"
  fi

  command -v python3 >/dev/null 2>&1 || die "未安装 python3"
}

prepare_files(){
  mkdir -p "$AIOPS_HOME" "$LOG_DIR"

  # app 源码包：由构建机生成并放入 offline/native/app.tar.gz（建议放 Release）
  local app_tar="$OFFLINE_DIR/native/app.tar.gz"
  [[ -f "$app_tar" ]] || die "缺少 $app_tar（请先在有网构建机生成 app.tar.gz 并放入 offline/native/）"

  rm -rf "$APP_DIR"
  mkdir -p "$APP_DIR"
  tar -xzf "$app_tar" -C "$APP_DIR" --strip-components=1

  # 生成配置
  if [[ ! -f "$ENV_FILE" ]]; then
    cp -n "$OFFLINE_DIR/config/aiops.env.example" "$ENV_FILE" || true
    log "已生成 $ENV_FILE（请按需修改）"
  fi

  # 强制私有化模式默认开启（你也可在 env 里关掉）
  if ! grep -q '^PRIVATE_DEPLOYMENT=' "$ENV_FILE"; then
    echo 'PRIVATE_DEPLOYMENT=true' >> "$ENV_FILE"
  fi

  # 默认原生模式使用 sqlite，避免离线装 MySQL
  if ! grep -q '^DATABASE_URL=' "$ENV_FILE"; then
    echo 'DATABASE_URL=sqlite:////opt/aiops/aiops.db' >> "$ENV_FILE"
  fi
}

setup_venv(){
  log "创建 venv"
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install --upgrade pip >/dev/null

  # wheelhouse：由构建机预下载放到 offline/native/wheelhouse
  local wh="$OFFLINE_DIR/native/wheelhouse"
  [[ -d "$wh" ]] || die "缺少 wheelhouse 目录：$wh"

  log "离线安装依赖（wheelhouse）"
  "$VENV_DIR/bin/pip" install --no-index --find-links "$wh" -r "$APP_DIR/requirements.txt"
}

install_systemd(){
  log "安装 systemd service"
  cat > /etc/systemd/system/aiops.service <<SERVICE
[Unit]
Description=Yueyun AIOps (private deployment)
After=network.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV_DIR/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3
StandardOutput=append:$LOG_DIR/aiops.log
StandardError=append:$LOG_DIR/aiops.err.log

[Install]
WantedBy=multi-user.target
SERVICE

  systemctl daemon-reload
  systemctl enable --now aiops
}

install_nginx(){
  # 反代 80 -> 8000
  if command -v nginx >/dev/null 2>&1; then
    log "配置 nginx 反代"
    cat > /etc/nginx/conf.d/aiops.conf <<'NG'
server {
  listen 80;
  server_name _;

  client_max_body_size 50m;

  location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
NG
    nginx -t
    systemctl enable --now nginx || true
    systemctl reload nginx || true
  fi
}

healthcheck(){
  log "健康检查"
  python3 - <<'PY'
import urllib.request, sys
for url in ("http://127.0.0.1/health", "http://127.0.0.1:8000/health"):
  try:
    with urllib.request.urlopen(url, timeout=5) as r:
      print(url, r.read().decode('utf-8', errors='ignore')[:200])
      sys.exit(0)
  except Exception as e:
    last=e
print('FAIL', last)
sys.exit(1)
PY
}

main(){
  require_root
  install_system_deps
  prepare_files
  setup_venv
  install_systemd
  install_nginx
  healthcheck || die "健康检查失败，请查看：$LOG_DIR/aiops.log"

  log "部署完成："
  log "- 登录地址：http://<服务器IP>/（80端口，nginx）"
  log "- 后端健康检查：http://<服务器IP>:8000/health"
  log "- 默认管理员账号：admin"
  log "- 默认管理员密码：admin@123A"
}

main "$@"
