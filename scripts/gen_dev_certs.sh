#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CERT_DIR="${1:-$PROJECT_ROOT/certs}"
DAYS="${DAYS:-3650}"

mkdir -p "$CERT_DIR"

OPENSSL_CONF_FILE="$CERT_DIR/openssl.cnf"
if [[ ! -f "$OPENSSL_CONF_FILE" ]]; then
cat > "$OPENSSL_CONF_FILE" <<'EOF'
[ req ]
default_bits = 2048
distinguished_name = req_distinguished_name
prompt = no

[ req_distinguished_name ]
C = CN
ST = Beijing
L = Beijing
O = ACPs-Demo
OU = Dev
CN = localhost
EOF
fi
export OPENSSL_CONF="$OPENSSL_CONF_FILE"

echo "[mTLS] generating dev CA in $CERT_DIR"
openssl genrsa -out "$CERT_DIR/ca.key" 4096
openssl req -x509 -new -nodes -key "$CERT_DIR/ca.key" -sha256 -days "$DAYS" \
  -out "$CERT_DIR/ca.crt" -subj "/C=CN/ST=Beijing/L=Beijing/O=ACPs-Demo/OU=Dev/CN=acps-dev-ca" \
  -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -addext "subjectKeyIdentifier=hash"

issue_cert() {
  local name="$1"
  local key_file="$CERT_DIR/${name}.key"
  local csr_file="$CERT_DIR/${name}.csr"
  local crt_file="$CERT_DIR/${name}.crt"
  local ext_file="$CERT_DIR/${name}.ext"

  openssl genrsa -out "$key_file" 2048
  openssl req -new -key "$key_file" -out "$csr_file" \
    -subj "/C=CN/ST=Beijing/L=Beijing/O=ACPs-Demo/OU=Dev/CN=${name}"
  cat > "$ext_file" <<EOF
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth,clientAuth
subjectAltName=DNS:${name},DNS:localhost,IP:127.0.0.1
EOF
  openssl x509 -req -in "$csr_file" -CA "$CERT_DIR/ca.crt" -CAkey "$CERT_DIR/ca.key" \
    -CAcreateserial -out "$crt_file" -days "$DAYS" -sha256 -extfile "$ext_file"
  rm -f "$csr_file"
  rm -f "$ext_file"
  echo "[mTLS] issued cert for $name"
}

# AIC-based names (used by fallback resolver)
issue_cert "reading_concierge_001"
issue_cert "reader_profile_agent_001"
issue_cert "book_content_agent_001"
issue_cert "rec_ranking_agent_001"

# Explicit mtls-path names used in config.example.json
issue_cert "reader_profile"
issue_cert "book_content"
issue_cert "rec_ranking"

echo "[mTLS] done. certs generated in $CERT_DIR"
