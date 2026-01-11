#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# GitHub Release 下载器（支持私有仓库）
# - 默认仓库：jingfanghua2025/aiops-private
# - 默认 tag：latest
# - 默认下载并解压：aiops-offline-images.tar.gz 到 offline/images/
#
# 用法：
#   ./download_release.sh                         # 拉取 latest 的默认 images 包
#   ./download_release.sh --tag v1.2.3            # 指定 tag
#   ./download_release.sh --repo org/repo         # 指定仓库
#   ./download_release.sh --asset xxx.tar.gz      # 指定资产文件名
#   GH_TOKEN=xxxx ./download_release.sh           # 私有仓库建议提供 token

REPO="jingfanghua2025/aiops-private"
TAG="latest"
ASSET="aiops-offline-images.tar.gz"
DEST_SUBDIR="images"

usage() {
  cat <<'USAGE'
Usage:
  ./download_release.sh [--repo org/repo] [--tag <tag|latest>] [--asset <name>] [--dest <subdir>]

Env:
  GH_TOKEN: GitHub token（私有仓库必需）

Examples:
  GH_TOKEN=xxx ./download_release.sh
  ./download_release.sh --tag v1.2.3 --asset aiops-offline-images.tar.gz
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="${2:-}"; shift 2;;
    --tag) TAG="${2:-}"; shift 2;;
    --asset) ASSET="${2:-}"; shift 2;;
    --dest) DEST_SUBDIR="${2:-}"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2;;
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

API_BASE="https://api.github.com"
REL_URL=""
if [[ "$TAG" == "latest" ]]; then
  REL_URL="$API_BASE/repos/$REPO/releases/latest"
else
  REL_URL="$API_BASE/repos/$REPO/releases/tags/$TAG"
fi

AUTH_HEADER=()
if [[ -n "${GH_TOKEN:-}" ]]; then
  AUTH_HEADER=(-H "Authorization: Bearer ${GH_TOKEN}")
fi

echo "[+] query release: repo=$REPO tag=$TAG"
REL_JSON="$(curl -fsSL "${AUTH_HEADER[@]}" -H "Accept: application/vnd.github+json" "$REL_URL")"

DOWNLOAD_URL="$(printf '%s' "$REL_JSON" | grep -Eo '\"browser_download_url\"\\s*:\\s*\"[^\"]+\"' | sed -E 's/.*\"([^\"]+)\"/\\1/' | grep -F "/$ASSET" | head -n1 || true)"
if [[ -z "$DOWNLOAD_URL" ]]; then
  echo "ERROR: 未找到 Release 资产：$ASSET" >&2
  echo "请确认 Release 已上传该文件，或用 --asset 指定正确文件名。" >&2
  exit 1
fi

mkdir -p "$DEST_SUBDIR"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

OUT="$TMP/$ASSET"

echo "[+] download: $ASSET"
curl -fL "${AUTH_HEADER[@]}" -o "$OUT" "$DOWNLOAD_URL"

echo "[+] extract -> $DEST_SUBDIR/"
tar -xzf "$OUT" -C "$DEST_SUBDIR"

echo "[+] done"
echo "你现在可以执行：sudo ./install.sh"

