#!/usr/bin/env bash
set -euo pipefail

echo "[+] verify health"
curl -fsS http://127.0.0.1/health | cat
echo

echo "[+] verify private_deployment flag"
curl -fsS http://127.0.0.1/api/v1/system/public | cat
echo

echo "[+] ok"

