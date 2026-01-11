#!/usr/bin/env bash
set -euo pipefail

# 交付方用：生成 GitHub Release 全量离线包（包含 offline/ + images/）
#
# 输出：
#   aiops-offline-bundle.tar.gz   （默认输出到当前目录）
#
# 约定：
# - 本脚本在仓库根目录执行：/path/to/aiops-private
# - 会把 ./offline 复制到临时目录，并在其中生成 images/*.tar.gz（docker save）
# - 不会把 .env / config/aiops.env / keys/*.pem 打进去（按 .gitignore 约定）
#
# 用法：
#   ./offline/release/make_offline_bundle.sh
#   OUT=./dist/aiops-offline-bundle.tar.gz ./offline/release/make_offline_bundle.sh
#   IMAGES_FILE=./offline/release/images.txt ./offline/release/make_offline_bundle.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

OUT="${OUT:-./aiops-offline-bundle.tar.gz}"
IMAGES_FILE="${IMAGES_FILE:-./offline/release/images.txt}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker 未安装" >&2
  exit 1
fi
if ! command -v tar >/dev/null 2>&1; then
  echo "ERROR: tar 未安装" >&2
  exit 1
fi

if [[ ! -d ./offline ]]; then
  echo "ERROR: 未找到 ./offline 目录" >&2
  exit 1
fi
if [[ ! -f "$IMAGES_FILE" ]]; then
  echo "ERROR: 未找到镜像清单：$IMAGES_FILE" >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "[+] prepare offline bundle workspace: $TMP"
mkdir -p "$TMP/offline"
rsync -a --delete \
  --exclude '.env' \
  --exclude 'config/aiops.env' \
  --exclude 'keys/*.pem' \
  --exclude 'images/*.tar' \
  --exclude 'images/*.tar.gz' \
  --exclude 'native/' \
  ./offline/ "$TMP/offline/"

mkdir -p "$TMP/offline/images"

echo "[+] docker save images -> $TMP/offline/images"
while IFS= read -r img; do
  img="$(echo "$img" | sed 's/#.*$//g' | xargs || true)"
  [[ -z "$img" ]] && continue

  echo "  - $img"
  if ! docker image inspect "$img" >/dev/null 2>&1; then
    echo "ERROR: 本机不存在镜像：$img（请先 docker pull 或构建）" >&2
    exit 1
  fi

  safe_name="$(echo "$img" | tr '/:' '__')"
  docker save "$img" | gzip -c > "$TMP/offline/images/${safe_name}.tar.gz"
done < "$IMAGES_FILE"

echo "[+] pack -> $OUT"
mkdir -p "$(dirname "$OUT")"
tar -czf "$OUT" -C "$TMP" offline

echo "[+] done: $OUT"
echo "请把该文件上传到 GitHub Release 资产里（建议命名：aiops-offline-bundle.tar.gz）"

