#!/usr/bin/env bash
set -euo pipefail

# Phase 3 official ATR certificate issuance helper.
# Requires a real ACPs ca-client installation.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

LEADER_AIC_DEFAULT="1.2.156.3088.0001.00001.U3IBA8.JI874M.1.03Y1"
PROFILE_AIC_DEFAULT="1.2.156.3088.0001.00001.FRMFWE.LBOY6M.1.1EGZ"
CONTENT_AIC_DEFAULT="1.2.156.3088.0001.00001.BPRK2Q.JLWHSY.1.06P9"
RANKING_AIC_DEFAULT="1.2.156.3088.0001.00001.09RLA8.91R7Z2.1.01CM"

CA_SERVER_BASE_URL="${CA_SERVER_BASE_URL:-http://bupt.ioa.pub:8003/acps-atr-v2}"
CHALLENGE_SERVER_BASE_URL="${CHALLENGE_SERVER_BASE_URL:-http://127.0.0.1:8004/acps-atr-v2}"
ACCOUNT_KEY_PATH="${ACCOUNT_KEY_PATH:-$PROJECT_ROOT/private/account.key}"
CERTS_DIR="${CERTS_DIR:-$PROJECT_ROOT/certs}"
PRIVATE_KEYS_DIR="${PRIVATE_KEYS_DIR:-$PROJECT_ROOT/private}"
CSR_DIR="${CSR_DIR:-$PROJECT_ROOT/csr}"
TRUST_BUNDLE_PATH="${TRUST_BUNDLE_PATH:-$PROJECT_ROOT/certs/trust-bundle.pem}"

mkdir -p "$CERTS_DIR" "$PRIVATE_KEYS_DIR" "$CSR_DIR" "$PROJECT_ROOT/artifacts/phase3"

if ! command -v ca-client >/dev/null 2>&1; then
  echo "[phase3][error] 'ca-client' command not found."
  echo "[phase3][hint] install official package first (example from ACPsProtocolGuide):"
  echo "  pip install acps_ca_client-2.0.0-py3-none-any.whl"
  exit 2
fi

CONF_PATH="$PROJECT_ROOT/ca-client.conf"
cat > "$CONF_PATH" <<EOF
CA_SERVER_BASE_URL = $CA_SERVER_BASE_URL
CHALLENGE_SERVER_BASE_URL = $CHALLENGE_SERVER_BASE_URL
ACCOUNT_KEY_PATH = $ACCOUNT_KEY_PATH
CERTS_DIR = $CERTS_DIR
PRIVATE_KEYS_DIR = $PRIVATE_KEYS_DIR
CSR_DIR = $CSR_DIR
TRUST_BUNDLE_PATH = $TRUST_BUNDLE_PATH
EOF

TIMESTAMP="$(date -u +"%Y%m%dT%H%M%SZ")"
LOG_PATH="$PROJECT_ROOT/artifacts/phase3/cert-issuance-$TIMESTAMP.log"

declare -a AICS=(
  "$LEADER_AIC_DEFAULT"
  "$PROFILE_AIC_DEFAULT"
  "$CONTENT_AIC_DEFAULT"
  "$RANKING_AIC_DEFAULT"
)

echo "[phase3] using config: $CONF_PATH" | tee -a "$LOG_PATH"
echo "[phase3] issuing certs for ${#AICS[@]} AICs..." | tee -a "$LOG_PATH"

for aic in "${AICS[@]}"; do
  echo "[phase3] ca-client new-cert --aic $aic" | tee -a "$LOG_PATH"
  ca-client new-cert --aic "$aic" | tee -a "$LOG_PATH"
done

echo "[phase3] certificate issuance finished. log=$LOG_PATH"
echo "[phase3] next: set AGENT_MTLS_ENABLED=true and run mTLS validation tests."
