#!/bin/sh
set -e

CERT_DIR="/etc/nginx/ssl"
SELF_SIGNED_KEY="${CERT_DIR}/privkey.pem"
SELF_SIGNED_CERT="${CERT_DIR}/fullchain.pem"

# ---- Always generate a self-signed cert as fallback ----
mkdir -p "${CERT_DIR}"
if [ ! -f "${SELF_SIGNED_CERT}" ]; then
  echo ">>> 生成自签证书（IP 模式备用）..."
  # Get the container's external IP for SAN（optional: pass IP via env）
  openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout "${SELF_SIGNED_KEY}" \
    -out "${SELF_SIGNED_CERT}" \
    -subj "/CN=localhost" \
    -addext "subjectAltName=IP:127.0.0.1,IP:0.0.0.0,DNS:localhost" 2>/dev/null
  echo ">>> 自签证书已生成（有效期 10 年）"
fi

# ---- Decide cert paths ----
CERT_KEY="${SELF_SIGNED_KEY}"
CERT_CHAIN="${SELF_SIGNED_CERT}"
CERT_MODE="self-signed"

if [ -n "${DOMAIN}" ] && [ -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]; then
  CERT_KEY="/etc/letsencrypt/live/${DOMAIN}/privkey.pem"
  CERT_CHAIN="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
  CERT_MODE="letsencrypt"
  echo ">>> 使用 Let's Encrypt 证书: ${DOMAIN}"
else
  echo ">>> 使用自签证书（浏览器会提示不安全，点击「继续访问」即可）"
fi

# ---- Generate nginx config ----
# Substitute CERT_KEY, CERT_CHAIN paths into template
export CERT_KEY CERT_CHAIN DOMAIN
envsubst '${CERT_KEY} ${CERT_CHAIN} ${DOMAIN}' \
  < /etc/nginx/templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf

echo ">>> nginx 启动 (mode=${CERT_MODE})"
exec nginx -g 'daemon off;'
