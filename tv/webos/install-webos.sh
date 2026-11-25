#!/usr/bin/env bash
set -euo pipefail

# Mavie LG webOS TV (4.0+) Sideloading Helper
# Usage: ./tv/webos/install-webos.sh [ARES_DEVICE_NAME]

DEVICE_NAME="${1:-lgtv}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
IPK_PATH="${REPO_ROOT}/dist/Mavie-webOS.ipk"

echo "[1/3] Mavie-webOS.ipk paketi oluşturuluyor..."
python3 "${REPO_ROOT}/tv/build_tv_packages.py"

if ! command -v ares-install >/dev/null 2>&1; then
  echo "[BİLGİ] 'ares-install' (webOS TV CLI) bulunamadı."
  echo "Grafik arayüzle kolay kurulum için 'webOS Dev Manager' uygulamasını açıp"
  echo "şu dosyayı sürükleyip bırakabilirsiniz:"
  echo "  ${IPK_PATH}"
  echo ""
  echo "CLI kurulumu için: npm install -g @webosose/ares-cli"
  echo "  ares-setup-device"
  echo "  ares-install --device ${DEVICE_NAME} ${IPK_PATH}"
  exit 1
fi

echo "[2/3] '${DEVICE_NAME}' cihazına yükleniyor..."
ares-install --device "${DEVICE_NAME}" "${IPK_PATH}"

echo "[3/3] Mavie TV başlatılıyor..."
ares-launch --device "${DEVICE_NAME}" app.mavie.tv || true
echo "[TAMAM] Mavie LG webOS TV'nize yüklendi! (Not: Developer Mode 1000 saatlik sayacını periyodik uzatmayı unutmayın.)"
