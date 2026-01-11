#!/usr/bin/env bash
set -euo pipefail

# 从 GitHub Release 下载离线交付大包（镜像/原生依赖），并解压到 offline/ 目录
#
# 用法：
#   cd /opt/aiops/offline
#   # 私有仓库建议设置 token（至少 read:packages / repo 下载权限）
#   export GH_TOKEN=xxxxx
#   # 默认仓库 jingfanghua2025/aiops-private
#   ./download_release.sh --tag latest
#
# 资产命名（建议）：
# - aiops-offline-images.tar.gz   -> 解压后包含 images/*.tar 或 images/*.tar.gz
# - aiops-offline-native.tar.gz   -> 解压后包含 native/*（可选）

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

OWNER_REPO_DEFAULT="jingfanghua2025/aiops-private"
OWNER_REPO="${OWNER_REPO:-$OWNER_REPO_DEFAULT}"
TAG="latest"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/.downloads}"

IMAGES_ASSET_REGEX="${IMAGES_ASSET_REGEX:-aiops-offline-images\\.tar\\.gz}"
NATIVE_ASSET_REGEX="${NATIVE_ASSET_REGEX:-aiops-offline-native\\.tar\\.gz}"

usage() {
  cat <<'EOF'
用法：
  ./download_release.sh [--repo owner/repo] [--tag latest|vX.Y.Z] [--out /path]

环境变量：
  GH_TOKEN               私有仓库/限流建议设置
  OWNER_REPO             默认 jingfanghua2025/aiops-private
  IMAGES_ASSET_REGEX     默认 aiops-offline-images\.tar\.gz
  NATIVE_ASSET_REGEX     默认 aiops-offline-native\.tar\.gz

示例：
  export GH_TOKEN=xxxxx
  ./download_release.sh --tag latest
  ./download_release.sh --tag v1.0.3
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --repo)
      OWNER_REPO="$2"; shift 2;;
    --tag)
      TAG="$2"; shift 2;;
    --out)
      OUT_DIR="$2"; shift 2;;
    -h|--help)
      usage; exit 0;;
    *)
      echo "未知参数：$1" >&2
      usage
      exit 2;;
  esac
done

if ! command -v curl >/dev/null 2>&1; then
  echo "ERROR: curl 未安装" >&2
  exit 1
fi
if ! command -v tar >/dev/null 2>&1; then
  echo "ERROR: tar 未安装" >&2
  exit 1
fi

API_URL=""
if [ "$TAG" = "latest" ]; then
  API_URL="https://api.github.com/repos/${OWNER_REPO}/releases/latest"
else
  API_URL="https://api.github.com/repos/${OWNER_REPO}/releases/tags/${TAG}"
fi

AUTH_HEADER=()
if [ -n "${GH_TOKEN:-}" ]; then
  AUTH_HEADER=(-H "Authorization: Bearer ${GH_TOKEN}")
fi

mkdir -p "$OUT_DIR" images native

echo "[+] fetch release metadata: ${OWNER_REPO} tag=${TAG}"
JSON="$(curl -fsSL "${AUTH_HEADER[@]}" -H "Accept: application/vnd.github+json" "$API_URL")"

extract_url_by_regex() {
  local regex="$1"
  # 提取第一个匹配资产的 browser_download_url
  echo "$JSON" | python3 - "$regex" <<'PY'
import json, re, sys
regex = re.compile(sys.argv[1])
j = json.load(sys.stdin)
assets = j.get("assets") or []
for a in assets:
    name = a.get("name","")
    if regex.search(name):
        print(a.get("browser_download_url",""))
        sys.exit(0)
print("")
PY
}

IMAGES_URL="$(extract_url_by_regex "$IMAGES_ASSET_REGEX")"
NATIVE_URL="$(extract_url_by_regex "$NATIVE_ASSET_REGEX")"

download() {
  local url="$1"
  local out="$2"
  if [ -z "$url" ]; then
    return 1
  fi
  echo "[+] download: $url"
  # 注意：私有仓库使用带 token 的直链下载也需要 Authorization
  curl -fL "${AUTH_HEADER[@]}" -o "$out" "$url"
}

OK_ANY=0
if [ -n "$IMAGES_URL" ]; then
  IMAGES_TAR="${OUT_DIR}/aiops-offline-images.tar.gz"
  download "$IMAGES_URL" "$IMAGES_TAR"
  echo "[+] extract images bundle -> ${ROOT_DIR}"
  tar -xzf "$IMAGES_TAR" -C "$ROOT_DIR"
  OK_ANY=1
else
  echo "[!] 未在 Release 资产中找到 images 包（regex=${IMAGES_ASSET_REGEX}）"
fi

if [ -n "$NATIVE_URL" ]; then
  NATIVE_TAR="${OUT_DIR}/aiops-offline-native.tar.gz"
  download "$NATIVE_URL" "$NATIVE_TAR"
  echo "[+] extract native bundle -> ${ROOT_DIR}"
  tar -xzf "$NATIVE_TAR" -C "$ROOT_DIR"
  OK_ANY=1
else
  echo "[i] 未找到 native 包（可选，regex=${NATIVE_ASSET_REGEX}）"
fi

if [ "$OK_ANY" -ne 1 ]; then
  echo "ERROR: 没有下载到任何离线交付包，请检查 Release 资产命名/Tag/权限（私有仓库需要 GH_TOKEN）" >&2
  exit 1
fi

echo "[+] done"
echo "下一步：修改 .env/config/aiops.env 后执行 ./install.sh"

