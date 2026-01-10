#!/usr/bin/env bash
set -euo pipefail

echo "[verify] systemd status"
systemctl status aiops --no-pager -l || true

echo "[verify] health"
curl -fsS --max-time 5 http://127.0.0.1:8000/health

echo "[verify] public info"
curl -fsS --max-time 5 http://127.0.0.1:8000/api/v1/system/public | head -c 500; echo

echo "OK"
