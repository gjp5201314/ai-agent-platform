#!/bin/bash
# ============================================================
# setup-https.sh — 首次申请 Let's Encrypt 证书
# ============================================================
# 在服务器上执行一次即可，之后 certbot 服务会自动续期。
#
# 用法（普通域名）:
#   DOMAIN=example.com CERT_EMAIL=you@email.com bash setup-https.sh
#
# 用法（DuckDNS，绕过防火墙）:
#   DOMAIN=xxx.duckdns.org DUCKDNS_TOKEN=your-token CERT_EMAIL=you@email.com bash setup-https.sh
#
# DuckDNS token 获取：https://www.duckdns.org 登录后页面顶部显示
# ============================================================
set -e

DOMAIN=${DOMAIN:?请设置 DOMAIN 环境变量}
CERT_EMAIL=${CERT_EMAIL:-admin@example.com}

STACK_NAME="${STACK_NAME:-ai-agent}"
CERTS_VOLUME="${STACK_NAME}_certs"
AUTH_HOOK="/opt/duckdns-auth.sh"

echo "============================================"
echo "  Let's Encrypt 证书初始化"
echo "  域名: ${DOMAIN}"
echo "  邮箱: ${CERT_EMAIL}"
if [ -n "${DUCKDNS_TOKEN}" ]; then
  echo "  模式: DNS (DuckDNS)"
else
  echo "  模式: HTTP (standalone)"
fi
echo "============================================"
echo ""

# ---- Step 1: 确保 certs volume 存在 ----
echo ">>> 检查 Docker volume..."
docker volume create "${CERTS_VOLUME}" 2>/dev/null || true

# ---- Step 2: 构建 certbot 参数 ----
CERT_EXTRA_ARGS=""
PAUSE_NGINX=true

if [ -n "${DUCKDNS_TOKEN}" ]; then
  # DNS challenge mode — no need to stop nginx
  PAUSE_NGINX=false
  CERT_EXTRA_ARGS="--preferred-challenges dns --manual --manual-auth-hook ${AUTH_HOOK} auth --manual-cleanup-hook ${AUTH_HOOK} cleanup"
  echo ">>> 使用 DNS 验证（不需要 80 端口）"
fi

# ---- Step 3: 暂停 nginx（仅 HTTP 模式需要） ----
if $PAUSE_NGINX; then
  echo ">>> 暂停 nginx 服务（释放 80 端口）..."
  docker service update --replicas=0 "${STACK_NAME}_frontend" 2>/dev/null || true
  sleep 3
fi

# ---- Step 4: 申请证书 ----
echo ">>> 申请证书..."

# Copy auth hook to a temp location that we mount into the container
TMP_AUTH=$(mktemp)
if [ -n "${DUCKDNS_TOKEN}" ]; then
  # Write auth hook with embedded token
  cat > "${TMP_AUTH}" << 'AUTHSCRIPT'
#!/bin/bash
set -e
SUBDOMAIN="${CERTBOT_DOMAIN%%.duckdns.org}"
if [ "$1" = "auth" ]; then
  echo ">>> DuckDNS TXT: _acme-challenge.${CERTBOT_DOMAIN} → ${CERTBOT_VALIDATION}"
  curl -sf "https://www.duckdns.org/update?domains=${SUBDOMAIN}&token=TOKEN_PLACEHOLDER&txt=${CERTBOT_VALIDATION}"
  echo ""
  echo ">>> 等待 DNS 传播 (60s)..."
  sleep 60
elif [ "$1" = "cleanup" ]; then
  echo ">>> 清除 DuckDNS TXT"
  curl -sf "https://www.duckdns.org/update?domains=${SUBDOMAIN}&token=TOKEN_PLACEHOLDER&txt=removed&clear=true" || true
  echo ""
fi
AUTHSCRIPT
  # Replace placeholder with actual token
  sed -i "s/TOKEN_PLACEHOLDER/${DUCKDNS_TOKEN}/g" "${TMP_AUTH}"
  chmod +x "${TMP_AUTH}"
fi

docker run --rm \
  -v "${CERTS_VOLUME}:/etc/letsencrypt" \
  ${PAUSE_NGINX:+-p 80:80} \
  ${DUCKDNS_TOKEN:+-v "${TMP_AUTH}:${AUTH_HOOK}:ro"} \
  certbot/certbot:latest \
  certonly \
    ${PAUSE_NGINX:+--standalone} \
    --non-interactive --agree-tos \
    -d "${DOMAIN}" \
    -m "${CERT_EMAIL}" \
    ${CERT_EXTRA_ARGS}

# Cleanup temp auth hook
[ -n "${DUCKDNS_TOKEN}" ] && rm -f "${TMP_AUTH}"

# ---- Step 5: 验证证书 ----
echo ">>> 验证证书..."
if docker run --rm -v "${CERTS_VOLUME}:/etc/letsencrypt" alpine \
   ls "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" > /dev/null 2>&1; then
  echo ">>> ✅ 证书已生成！"
else
  echo ">>> ❌ 证书申请失败。"
  if [ -n "${DUCKDNS_TOKEN}" ]; then
    echo ""
    echo "   可能原因："
    echo "   1. DuckDNS token 是否正确？"
    echo "   2. 域名 ${DOMAIN} 是否在 DuckDNS 上创建？"
    echo "   3. 等待 DNS 生效后再试（有时需要几分钟）"
    echo ""
    echo "   手动验证："
    echo "   curl 'https://www.duckdns.org/update?domains=${DOMAIN%%.duckdns.org}&token=YOUR_TOKEN&txt=test'"
  fi
  $PAUSE_NGINX && docker service update --replicas=1 "${STACK_NAME}_frontend" 2>/dev/null || true
  exit 1
fi

# ---- Step 6: 创建 webroot 结构（供后续 certbot renew 使用） ----
echo ">>> 创建 webroot..."
docker run --rm \
  -v "${CERTS_VOLUME}:/etc/letsencrypt" \
  -v "${STACK_NAME}_certbot_webroot:/var/www/certbot" \
  alpine sh -c "mkdir -p /var/www/certbot/.well-known/acme-challenge"

# ---- Step 7: 重启 nginx（现在会检测到证书并开启 HTTPS） ----
echo ">>> 恢复/重启 nginx 服务..."
docker service update --replicas=1 --force "${STACK_NAME}_frontend" 2>/dev/null || true

echo ""
echo "============================================"
echo "  ✅ HTTPS 证书已配置！"
echo "  访问: https://${DOMAIN}"
echo "  证书将在到期前自动续期（certbot 每 12h 检查）"
echo "============================================"
