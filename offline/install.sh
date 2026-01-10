#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

log() { echo "[$(date +'%F %T')] $*" | tee -a "$LOG_DIR/install.log"; }
die() { log "ERROR: $*"; exit 1; }

require_root() {
  if [[ "$(id -u)" != "0" ]]; then
    die "请用 root 执行（或 sudo）"
  fi
}

os_detect() {
  if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    echo "${ID:-unknown}" "${VERSION_ID:-unknown}"
  else
    echo unknown unknown
  fi
}

has_cmd() { command -v "$1" >/dev/null 2>&1; }

ensure_docker() {
  if has_cmd docker; then
    log "Docker 已存在：$(docker --version 2>/dev/null || true)"
  else
    log "Docker 未安装，尝试使用离线包安装"
    read -r os_id os_ver < <(os_detect)
    if [[ "$os_id" =~ (ubuntu|debian) ]]; then
      local pkg_dir="$ROOT_DIR/packages/ubuntu"
      ls "$pkg_dir"/*.deb >/dev/null 2>&1 || die "未找到 Ubuntu 离线 deb 包：$pkg_dir"
      dpkg -i "$pkg_dir"/*.deb || die "dpkg 安装失败（可能缺依赖，请把依赖 deb 一并放入 $pkg_dir）"
    elif [[ "$os_id" =~ (centos|rhel|rocky|almalinux) ]]; then
      local pkg_dir=""
      # CentOS7 与 Rocky8/9 的包目录不同
      if [[ -d "$ROOT_DIR/packages/centos7" ]]; then
        pkg_dir="$ROOT_DIR/packages/centos7"
      elif [[ -d "$ROOT_DIR/packages/rocky" ]]; then
        pkg_dir="$ROOT_DIR/packages/rocky"
      else
        pkg_dir="$ROOT_DIR/packages/centos"
      fi
      ls "$pkg_dir"/*.rpm >/dev/null 2>&1 || die "未找到 CentOS/RHEL 离线 rpm 包：$pkg_dir"
      rpm -Uvh --force "$pkg_dir"/*.rpm || die "rpm 安装失败"
    else
      die "不支持的系统：$os_id $os_ver（仅支持 Ubuntu/Debian 与 CentOS/RHEL 系）"
    fi
  fi

  systemctl enable --now docker >/dev/null 2>&1 || true
  if ! docker info >/dev/null 2>&1; then
    die "Docker daemon 未就绪，请检查：systemctl status docker"
  fi

  # docker compose 优先
  if has_cmd docker && docker compose version >/dev/null 2>&1; then
    log "docker compose 可用"
  elif has_cmd docker-compose; then
    log "docker-compose 可用"
  else
    log "未检测到 compose，尝试离线安装 docker compose 插件"
    # 插件通常随 docker-compose-plugin 安装；这里仅提示
    die "缺少 docker compose。请在离线包中加入 docker-compose-plugin(ubuntu) 或 docker-compose(centos)"
  fi
}

load_images() {
  local img_dir="$ROOT_DIR/images"
  if compgen -G "$img_dir/*.tar" >/dev/null; then
    log "开始导入离线镜像"
    for f in "$img_dir"/*.tar; do
      log "docker load: $f"
      docker load -i "$f" >/dev/null
    done
  else
    die "未找到离线镜像 tar：$img_dir/*.tar"
  fi
}

prepare_runtime_files() {
  mkdir -p "$ROOT_DIR"/{db,nginx/conf.d,www,static,keys}

  if [[ ! -f "$ROOT_DIR/config/aiops.env" ]]; then
    cp -n "$ROOT_DIR/config/aiops.env.example" "$ROOT_DIR/config/aiops.env" || true
    log "已生成配置模板：$ROOT_DIR/config/aiops.env（请按需修改）"
  fi

  if [[ ! -f "$ROOT_DIR/db/db_dump.sql" ]]; then
    # 如果你希望带初始化库，把 dump 放到这里
    log "提示：未发现 db/db_dump.sql，将以空库启动（或你自行放入初始化 SQL）"
  fi

  if [[ ! -f "$ROOT_DIR/keys/license_public.pem" ]]; then
    log "提示：未发现 keys/license_public.pem（公钥）。license 激活校验会失败，请补齐后再启用 license。"
  fi
}

compose_up() {
  log "启动服务（docker compose up -d）"
  if docker compose version >/dev/null 2>&1; then
    (cd "$ROOT_DIR" && docker compose up -d)
  else
    (cd "$ROOT_DIR" && docker-compose up -d)
  fi
}

healthcheck() {
  log "健康检查：/health"
  python3 - <<'PY'
import urllib.request, sys
for url in ("http://127.0.0.1/health", "http://127.0.0.1:8000/health"):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            body = r.read().decode('utf-8', errors='ignore')
        print("OK", url, body[:200])
        sys.exit(0)
    except Exception as e:
        last = e
print("FAIL", last)
sys.exit(1)
PY
}

main() {
  require_root
  log "AIOps 私有化离线一键部署开始（适配 Ubuntu/CentOS）"
  ensure_docker
  prepare_runtime_files
  load_images
  compose_up
  healthcheck || die "健康检查失败，请查看 logs/install.log 与 docker logs"
  log "部署完成："
  log "- 登录地址：http://<服务器IP>/ （80端口，Nginx）"
  log "- 后端健康检查：http://<服务器IP>:8000/health"
  log "- 默认管理员账号：admin"
  log "- 默认管理员密码：admin@123A"
  log "建议首次登录后立即在【用户管理】中重置管理员密码，并创建普通用户。"
}

main "$@"
