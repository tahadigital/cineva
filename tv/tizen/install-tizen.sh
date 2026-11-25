#!/usr/bin/env bash
set -euo pipefail

# Mavie Samsung Tizen TV (TU8500 / Tizen 5.5+) Sideloading Helper
# Usage: ./tv/tizen/install-tizen.sh <TV_IP> [SECURITY_PROFILE]

TV_IP="${1:-}"
PROFILE="${2:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
WGT_PATH="${REPO_ROOT}/dist/Mavie-Tizen.wgt"

if [[ -z "${TV_IP}" ]]; then
  echo "Kullanım: $0 <TV_IP_ADRESI> [SERTIFIKA_PROFILI]"
  echo "Örnek   : $0 192.168.1.42 MavieProfile"
  echo ""
  echo "Ön Koşullar (Samsung TU8500 / Tizen 5.5+):"
  echo "  1) TV'de Apps ekranında kumandadan 12345 tuşlayın."
  echo "  2) Developer Mode: ON yapın, Host PC IP alanına bilgisayarınızın IP'sini girin."
  echo "  3) TV'yi güç tuşuna 5 sn basılı tutarak tamamen yeniden başlatın."
  exit 1
fi

if ! command -v sdb >/dev/null 2>&1 || ! command -v tizen >/dev/null 2>&1; then
  echo "[HATA] 'sdb' ve 'tizen' (Tizen Studio CLI) PATH içinde bulunamadı."
  echo "Alternatif olarak Docker kurulumunu kullanabilirsiniz:"
  echo "  docker build -t mavie-tizen tv/tizen && docker run --rm --network host mavie-tizen ${TV_IP}"
  exit 1
fi

echo "[1/5] Mavie-Tizen.wgt paketi oluşturuluyor..."
python3 "${REPO_ROOT}/tv/build_tv_packages.py"

echo "[2/5] Samsung TV'ye bağlanılıyor (${TV_IP}:26101)..."
sdb connect "${TV_IP}"
DEVICE_ID="$(sdb devices | awk '/device/ {print $1; exit}')"
if [[ -z "${DEVICE_ID}" ]]; then
  echo "[HATA] TV bağlantısı kurulamadı. Developer Mode, Host PC IP ve aynı Wi-Fi ağını kontrol edin."
  exit 1
fi
echo "      Bağlı cihaz: ${DEVICE_ID}"

DUID="$(sdb -s "${DEVICE_ID}" shell 0 getduid 2>/dev/null | tr -d '\r\n' || true)"
if [[ -n "${DUID}" ]]; then
  echo "      TV DUID    : ${DUID}"
fi

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "${WORK_DIR}"' EXIT
unzip -q "${WGT_PATH}" -d "${WORK_DIR}/app"

if [[ -n "${PROFILE}" ]]; then
  echo "[3/5] '${PROFILE}' sertifika profili ile imzalanıyor..."
  tizen package -t wgt -s "${PROFILE}" -o "${WORK_DIR}" -- "${WORK_DIR}/app"
  SIGNED_WGT="$(ls -1 "${WORK_DIR}"/*.wgt | head -n 1)"
else
  echo "[3/5] Varsayılan aktif Tizen sertifika profili ile imzalanıyor..."
  tizen package -t wgt -o "${WORK_DIR}" -- "${WORK_DIR}/app"
  SIGNED_WGT="$(ls -1 "${WORK_DIR}"/*.wgt | head -n 1)"
fi

echo "[4/5] Eski geliştirici sürümü varsa temizleniyor..."
tizen uninstall -p MavieTV001.Mavie -t "${DEVICE_ID}" >/dev/null 2>&1 || true

echo "[5/5] Mavie TV'ye yükleniyor..."
tizen install -n "${SIGNED_WGT}" -t "${DEVICE_ID}"
echo ""
echo "[TAMAM] Mavie Samsung TV'nize yüklendi! TV'de Apps ekranından Mavie'yi açabilirsiniz."
