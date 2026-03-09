#!/usr/bin/env bash
set -e

PROJECT_DIR=/opt/vpn-bot

echo "Deploying MOROZ VPN Bot to ${PROJECT_DIR}..."

mkdir -p "${PROJECT_DIR}"
cp -r . "${PROJECT_DIR}/"

cd "${PROJECT_DIR}"

echo "Installing Python dependencies..."
python3 -m pip install -r requirements.txt

echo "Building frontend..."
cd web_admin/frontend
npm install
npm run build

echo "Installing systemd services..."
cd "${PROJECT_DIR}"
cp deploy/systemd/vpn-bot.service /etc/systemd/system/
cp deploy/systemd/vpn-web-admin.service /etc/systemd/system/
cp deploy/systemd/vpn-traffic-snapshots.service /etc/systemd/system/
cp deploy/systemd/vpn-traffic-snapshots.timer /etc/systemd/system/

systemctl daemon-reload
systemctl enable --now vpn-bot.service
systemctl enable --now vpn-web-admin.service
systemctl enable --now vpn-traffic-snapshots.timer

echo "Deploy complete."

