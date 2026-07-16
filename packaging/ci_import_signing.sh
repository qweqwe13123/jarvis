#!/bin/zsh
# Import Developer ID + App Store Connect API key for GitHub Actions / CI.
# Required secrets (base64 where noted):
#   MACOS_CERTIFICATE_P12_BASE64
#   MACOS_CERTIFICATE_PASSWORD
#   APPLE_API_KEY_BASE64          (.p8 contents, base64)
#   APPLE_API_KEY_ID
#   APPLE_API_ISSUER
#   AURA_CODESIGN_IDENTITY       (optional override)
set -euo pipefail

KEYCHAIN_NAME="${AURA_CI_KEYCHAIN:-aura-signing.keychain-db}"
KEYCHAIN_PASSWORD="${AURA_CI_KEYCHAIN_PASSWORD:-$(openssl rand -base64 24)}"
PROFILE="${AURA_NOTARY_PROFILE:-AURA-notarize}"
CERT_PATH="${RUNNER_TEMP:-/tmp}/aura_developer_id.p12"
API_KEY_PATH="${RUNNER_TEMP:-/tmp}/AuthKey_${APPLE_API_KEY_ID:-CI}.p8"

if [[ -z "${MACOS_CERTIFICATE_P12_BASE64:-}" ]]; then
  echo "MACOS_CERTIFICATE_P12_BASE64 is required"
  exit 1
fi
if [[ -z "${MACOS_CERTIFICATE_PASSWORD:-}" ]]; then
  echo "MACOS_CERTIFICATE_PASSWORD is required"
  exit 1
fi
if [[ -z "${APPLE_API_KEY_BASE64:-}" || -z "${APPLE_API_KEY_ID:-}" || -z "${APPLE_API_ISSUER:-}" ]]; then
  echo "APPLE_API_KEY_BASE64, APPLE_API_KEY_ID, APPLE_API_ISSUER are required for notarization"
  exit 1
fi

echo "=== Create temporary keychain ==="
security create-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN_NAME" || true
security set-keychain-settings -lut 21600 "$KEYCHAIN_NAME"
security unlock-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN_NAME"

echo "=== Import Developer ID certificate ==="
echo "$MACOS_CERTIFICATE_P12_BASE64" | base64 --decode > "$CERT_PATH"
security import "$CERT_PATH" \
  -P "$MACOS_CERTIFICATE_PASSWORD" \
  -A \
  -t cert \
  -f pkcs12 \
  -k "$KEYCHAIN_NAME"
security list-keychain -d user -s "$KEYCHAIN_NAME" login.keychain-db
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$KEYCHAIN_PASSWORD" "$KEYCHAIN_NAME"

echo "=== Store notarytool API credentials ==="
echo "$APPLE_API_KEY_BASE64" | base64 --decode > "$API_KEY_PATH"
xcrun notarytool store-credentials "$PROFILE" \
  --key "$API_KEY_PATH" \
  --key-id "$APPLE_API_KEY_ID" \
  --issuer "$APPLE_API_ISSUER" \
  --keychain "$KEYCHAIN_NAME"

# Export for subsequent steps
echo "AURA_CI_KEYCHAIN=$KEYCHAIN_NAME" >> "${GITHUB_ENV:-/dev/null}"
echo "AURA_NOTARY_PROFILE=$PROFILE" >> "${GITHUB_ENV:-/dev/null}"
echo "KEYCHAIN_PASSWORD=$KEYCHAIN_PASSWORD" >> "${GITHUB_ENV:-/dev/null}"

echo "=== Available signing identities ==="
security find-identity -v -p codesigning "$KEYCHAIN_NAME" || security find-identity -v -p codesigning

rm -f "$CERT_PATH"
echo "✅ CI signing credentials ready (profile=$PROFILE)"
