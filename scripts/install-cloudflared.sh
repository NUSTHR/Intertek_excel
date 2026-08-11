#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="${CLOUDFLARED_INSTALL_DIR:-${PROJECT_ROOT}/.tools}"
VERSION="${CLOUDFLARED_VERSION:-2026.5.2}"
SYSTEM="$(uname -s)"
MACHINE="$(uname -m)"

case "${SYSTEM}:${MACHINE}" in
  Darwin:arm64)
    ASSET="cloudflared-darwin-arm64.tgz"
    EXPECTED_SHA256="ba94054c9fd4297645093d59d51442e5e546d07bb0516120e694a13d5b216d38"
    ;;
  Darwin:x86_64)
    ASSET="cloudflared-darwin-amd64.tgz"
    EXPECTED_SHA256="7240f709506bc2c1eb9da4d89cf2555499c60280ecb854b7d80e8f17d4b7903d"
    ;;
  *)
    echo "Unsupported platform: ${SYSTEM} ${MACHINE}."
    echo "Install cloudflared from https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
    exit 1
    ;;
esac

for dependency in curl tar shasum; do
  if ! command -v "${dependency}" >/dev/null 2>&1; then
    echo "Required command is missing: ${dependency}"
    exit 1
  fi
done

DOWNLOAD_URL="https://github.com/cloudflare/cloudflared/releases/download/${VERSION}/${ASSET}"
TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/cloudflared-install.XXXXXX")"
ARCHIVE_PATH="${TEMP_DIR}/${ASSET}"

cleanup() {
  rm -rf "${TEMP_DIR}"
}
trap cleanup EXIT

echo "Downloading cloudflared ${VERSION} for ${SYSTEM} ${MACHINE}..."
curl --fail --location --retry 3 --output "${ARCHIVE_PATH}" "${DOWNLOAD_URL}"

ACTUAL_SHA256="$(shasum -a 256 "${ARCHIVE_PATH}" | awk '{print $1}')"
if [[ "${ACTUAL_SHA256}" != "${EXPECTED_SHA256}" ]]; then
  echo "cloudflared checksum verification failed."
  echo "Expected: ${EXPECTED_SHA256}"
  echo "Actual:   ${ACTUAL_SHA256}"
  exit 1
fi

tar -xzf "${ARCHIVE_PATH}" -C "${TEMP_DIR}"
if [[ ! -f "${TEMP_DIR}/cloudflared" ]]; then
  echo "The downloaded archive did not contain cloudflared."
  exit 1
fi

mkdir -p "${INSTALL_DIR}"
install -m 0755 "${TEMP_DIR}/cloudflared" "${INSTALL_DIR}/cloudflared"
"${INSTALL_DIR}/cloudflared" --version
echo "Installed: ${INSTALL_DIR}/cloudflared"
