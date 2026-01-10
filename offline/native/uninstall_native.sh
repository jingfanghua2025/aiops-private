#!/usr/bin/env bash
set -euo pipefail
[[ "$(id -u)" == "0" ]] || { echo "请用 root"; exit 1; }

systemctl stop aiops 2>/dev/null || true
systemctl disable aiops 2>/dev/null || true
rm -f /etc/systemd/system/aiops.service
systemctl daemon-reload

rm -rf /opt/aiops

echo "已卸载原生部署"
