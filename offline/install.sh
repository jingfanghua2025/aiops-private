#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "[+] AIOps+ offline one-click deploy (docker)"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker 未安装" >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: docker compose 不可用（请安装 docker compose plugin）" >&2
  exit 1
fi

mkdir -p logs keys patches static nginx/conf.d images config

if [ ! -f .env ]; then
  echo "[!] 未找到 .env，已从 .env.example 生成"
  cp .env.example .env
fi
if [ ! -f config/aiops.env ]; then
  echo "[!] 未找到 config/aiops.env，已从模板生成"
  cp config/aiops.env.example config/aiops.env
fi

echo "[+] load offline images (optional)"
shopt -s nullglob
for tar in images/*.tar images/*.tar.gz; do
  echo "  - loading $tar"
  if [[ "$tar" == *.tar.gz ]]; then
    gunzip -c "$tar" | docker load
  else
    docker load -i "$tar"
  fi
done

echo "[+] docker compose up -d"
docker compose up -d

echo "[+] wait for health..."
for i in {1..30}; do
  if curl -fsS --max-time 2 http://127.0.0.1/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

curl -fsS http://127.0.0.1/health
curl -fsS http://127.0.0.1/api/v1/system/public

echo
echo "OK: 访问 http://<server_ip>/"

