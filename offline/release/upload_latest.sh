#!/usr/bin/env bash
set -euo pipefail

# 交付方用：把离线包上传到 GitHub Release（tag=latest）
#
# 依赖：
# - curl
# - python3
#
# 用法：
#   export GH_TOKEN=xxxxx
#   ./offline/release/upload_latest.sh ./aiops-offline-bundle.tar.gz
#
# 可选：
#   REPO=jingfanghua2025/aiops-private ./offline/release/upload_latest.sh ./aiops-offline-bundle.tar.gz
#   TAG=latest ./offline/release/upload_latest.sh ...

REPO="${REPO:-jingfanghua2025/aiops-private}"
TAG="${TAG:-latest}"
BUNDLE_PATH="${1:-}"

if [[ -z "$BUNDLE_PATH" ]]; then
  echo "Usage: $0 /path/to/aiops-offline-bundle.tar.gz" >&2
  exit 2
fi
if [[ -z "${GH_TOKEN:-}" ]]; then
  echo "ERROR: GH_TOKEN 未设置（私有仓库必须）" >&2
  exit 2
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "ERROR: curl 未安装" >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 未安装" >&2
  exit 1
fi
if [[ ! -f "$BUNDLE_PATH" ]]; then
  echo "ERROR: 文件不存在：$BUNDLE_PATH" >&2
  exit 1
fi

API="https://api.github.com"
AUTH=(-H "Authorization: Bearer ${GH_TOKEN}" -H "Accept: application/vnd.github+json")

echo "[+] ensure release exists: $REPO tag=$TAG"

# 1) find or create release
REL_JSON="$(curl -fsSL "${AUTH[@]}" "$API/repos/$REPO/releases/tags/$TAG" || true)"
REL_ID="$(python3 - <<'PY'
import json,sys
s=sys.stdin.read().strip()
if not s:
  print("")
  sys.exit(0)
try:
  j=json.loads(s)
except Exception:
  print("")
  sys.exit(0)
print(j.get("id",""))
PY
<<<"$REL_JSON")"

if [[ -z "$REL_ID" ]]; then
  echo "[+] release not found, creating..."
  CREATE_JSON="$(python3 - <<PY
import json
print(json.dumps({
  "tag_name": "$TAG",
  "name": "$TAG",
  "draft": False,
  "prerelease": False
}))
PY
)"
  REL_JSON="$(curl -fsSL -X POST "${AUTH[@]}" -H "Content-Type: application/json" \
    -d "$CREATE_JSON" "$API/repos/$REPO/releases")"
  REL_ID="$(python3 - <<'PY'
import json,sys
j=json.loads(sys.stdin.read())
print(j["id"])
PY
<<<"$REL_JSON")"
fi

echo "[+] release id=$REL_ID"

UPLOAD_URL="https://uploads.github.com/repos/$REPO/releases/$REL_ID/assets"

upload_asset () {
  local path="$1"
  local name="$2"
  local ctype="$3"

  echo "[+] upload asset: $name ($(du -h "$path" | awk '{print $1}'))"
  # 如果已存在同名资产，先删除
  local assets_json
  assets_json="$(curl -fsSL "${AUTH[@]}" "$API/repos/$REPO/releases/$REL_ID/assets")"
  local asset_id
  asset_id="$(python3 - <<'PY'
import json,sys,os
j=json.loads(sys.stdin.read())
name=os.environ["ASSET_NAME"]
for a in j:
  if a.get("name")==name:
    print(a.get("id",""))
    break
PY
<<<"$assets_json" ASSET_NAME="$name")"

  if [[ -n "$asset_id" ]]; then
    echo "[+] asset exists, delete id=$asset_id"
    curl -fsSL -X DELETE "${AUTH[@]}" "$API/repos/$REPO/releases/assets/$asset_id" >/dev/null
  fi

  curl -fL -X POST "${AUTH[@]}" \
    -H "Content-Type: $ctype" \
    --data-binary @"$path" \
    "$UPLOAD_URL?name=$name" >/dev/null
}

bundle_name="$(basename "$BUNDLE_PATH")"
upload_asset "$BUNDLE_PATH" "$bundle_name" "application/gzip"

if [[ -f "${BUNDLE_PATH}.sha256" ]]; then
  upload_asset "${BUNDLE_PATH}.sha256" "${bundle_name}.sha256" "text/plain"
fi

echo "[+] done"
echo "Release: https://github.com/$REPO/releases/tag/$TAG"

