#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log(){ echo "[$(date +'%F %T')] $*"; }

has_cmd(){ command -v "$1" >/dev/null 2>&1; }

curl_json(){
  local url="$1"
  curl -fsS --max-time 5 "$url"
}

require(){
  local msg="$1"
  shift
  if ! "$@"; then
    echo "FAIL: $msg" >&2
    exit 1
  fi
  echo "OK: $msg"
}

log "AIOps 私有化离线验收开始"

# OS
if [[ -f /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  log "OS: ${PRETTY_NAME:-$ID $VERSION_ID}"
fi

# docker
require "docker 已安装" has_cmd docker
log "docker: $(docker --version 2>/dev/null || true)"
require "docker daemon 可用" docker info >/dev/null 2>&1

# compose
if docker compose version >/dev/null 2>&1; then
  log "docker compose: $(docker compose version)"
  COMPOSE="docker compose"
elif has_cmd docker-compose; then
  log "docker-compose: $(docker-compose --version)"
  COMPOSE="docker-compose"
else
  echo "FAIL: 缺少 docker compose" >&2
  exit 1
fi

# containers
log "检查容器状态"
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

require "aiops-backend 容器存在" docker ps -a --format '{{.Names}}' | grep -qx aiops-backend
require "aiops-mysql 容器存在" docker ps -a --format '{{.Names}}' | grep -qx aiops-mysql
require "aiops-nginx 容器存在" docker ps -a --format '{{.Names}}' | grep -qx aiops-nginx

require "aiops-backend 运行中" docker ps --format '{{.Names}}' | grep -qx aiops-backend
require "aiops-mysql 运行中" docker ps --format '{{.Names}}' | grep -qx aiops-mysql
require "aiops-nginx 运行中" docker ps --format '{{.Names}}' | grep -qx aiops-nginx

# ports
log "检查端口监听"
if has_cmd ss; then
  ss -lntp | egrep ':80\s|:8000\s|:3306\s' || true
elif has_cmd netstat; then
  netstat -lntp | egrep ':80\s|:8000\s|:3306\s' || true
fi

# health
log "检查 /health"
require "/health (nginx 80) 可访问" curl -fsS --max-time 5 http://127.0.0.1/health >/dev/null
require "/health (backend 8000) 可访问" curl -fsS --max-time 5 http://127.0.0.1:8000/health >/dev/null

# public info
log "检查 /api/v1/system/public"
PUB_JSON=$(curl_json http://127.0.0.1/api/v1/system/public || true)
if [[ -z "$PUB_JSON" ]]; then
  echo "FAIL: system/public 无法访问" >&2
  exit 1
fi

echo "$PUB_JSON" | head -c 500; echo

echo "$PUB_JSON" | grep -q '"private_deployment"' || { echo "FAIL: public_info 缺少 private_deployment"; exit 1; }

echo "$PUB_JSON" | grep -q '"private_deployment"\s*:\s*true' && echo "OK: private_deployment=true" || echo "WARN: private_deployment 不是 true（请检查 config/aiops.env）"

# login with default admin
log "管理员登录（默认：admin / admin@123A）"
TOKEN_JSON=$(curl -fsS --max-time 8 -X POST http://127.0.0.1/api/v1/auth/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=admin' \
  --data-urlencode 'password=admin@123A' || true)

if [[ -z "$TOKEN_JSON" ]]; then
  echo "FAIL: 管理员登录失败（可能 license 到期或密码已改）" >&2
  exit 1
fi

echo "$TOKEN_JSON" | head -c 200; echo

ACCESS_TOKEN=$(echo "$TOKEN_JSON" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)
if [[ -z "$ACCESS_TOKEN" ]]; then
  echo "FAIL: 未获取到 access_token" >&2
  exit 1
fi

# admin endpoints
log "检查管理员接口：用户列表、系统设置"
require "GET /system/users 200" curl -fsS --max-time 8 -H "Authorization: Bearer $ACCESS_TOKEN" http://127.0.0.1/api/v1/system/users >/dev/null
require "GET /system/settings 200" curl -fsS --max-time 8 -H "Authorization: Bearer $ACCESS_TOKEN" http://127.0.0.1/api/v1/system/settings >/dev/null
require "GET /system/license/request 200" curl -fsS --max-time 8 -H "Authorization: Bearer $ACCESS_TOKEN" http://127.0.0.1/api/v1/system/license/request >/dev/null

# disabled endpoints in private deployment
log "检查私有化禁用接口（应返回 404）"
code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1/api/v1/auth/register)
[[ "$code" == "404" ]] && echo "OK: /auth/register 已禁用" || echo "WARN: /auth/register code=$code（期望 404）"

code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $ACCESS_TOKEN" http://127.0.0.1/api/v1/dashboard/stats)
[[ "$code" == "404" ]] && echo "OK: /dashboard/stats 已禁用" || echo "WARN: /dashboard/stats code=$code（期望 404）"

log "验收完成：OK"
