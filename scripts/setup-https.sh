#!/bin/bash
# ============================================================
# setup-https.sh — 首次申请 Let's Encrypt 证书
# ============================================================
# 在服务器上执行一次即可，之后 certbot 服务会自动续期。
#
# 用法:
#   DOMAIN=your-domain.com CERT_EMAIL=you@email.com bash setup-https.sh
#
# 前提:
#   - 域名 DNS 已指向本服务器 IP
#   - 防火墙已开放 80/443 端口
# ============================================================
set -e

DOMAIN=${DOMAIN:?请设置 DOMAIN 环境变量，例如 DOMAIN=ai.example.com}
CERT_EMAIL=${CERT_EMAIL:-admin@example.com}

STACK_NAME="${STACK_NAME:-ai-agent}"
CERTS_VOLUME="${STACK_NAME}_certs"

echo "============================================"
echo "  Let's Encrypt 证书初始化"
echo "  域名: ${DOMAIN}"
echo "  邮箱: ${CERT_EMAIL}"
echo "============================================"
echo ""

# ---- Step 1: 确保 certs volume 存在 ----
echo ">>> 检查 Docker volume..."
docker volume create "${CERTS_VOLUME}" 2>/dev/null || true

# ---- Step 2: 临时关闭 nginx（certbot standalone 需要 80 端口） ----
echo ">>> 暂停 nginx 服务（释放 80 端口）..."
docker service update --replicas=0 "${STACK_NAME}_frontend" 2>/dev/null || true
sleep 3

# ---- Step 3: 申请证书 ----
echo ">>> 申请证书..."
docker run --rm \
  -v "${CERTS_VOLUME}:/etc/letsencrypt" \
  -p 80:80 \
  certbot/certbot:latest \
  certonly --standalone \
    --non-interactive --agree-tos \
    -d "${DOMAIN}" \
    -m "${CERT_EMAIL}"

if [ ! -d "/var/lib/docker/volumes/${CERTS_VOLUME}/_data/live/${DOMAIN}" ]; then
  # Check inside container
  if docker run --rm -v "${CERTS_VOLUME}:/etc/letsencrypt" alpine ls "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" > /dev/null 2>&1; then
    echo ">>> 证书已生成！"
  else
    echo ">>> ❌ 证书申请失败，请检查："
    echo "   1. DOMAIN=${DOMAIN} 的 DNS A 记录是否指向本服务器 IP"
    echo "   2. 80 端口是否未被占用: ss -tlnp | grep :80"
    echo "   3. 防火墙是否开放 80 端口"
    docker service update --replicas=1 "${STACK_NAME}_frontend" 2>/dev/null || true
    exit 1
  fi
fi

# ---- Step 4: 创建 webroot 结构（供后续 certbot renew 使用） ----
echo ">>> 创建 webroot..."
docker run --rm \
  -v "${CERTS_VOLUME}:/etc/letsencrypt" \
  -v "${STACK_NAME}_certbot_webroot:/var/www/certbot" \
  alpine sh -c "mkdir -p /var/www/certbot/.well-known/acme-challenge"

# ---- Step 5: 重启 nginx（现在会检测到证书并开启 HTTPS） ----
echo ">>> 恢复 nginx 服务..."
docker service update --replicas=1 --force "${STACK_NAME}_frontend" 2>/dev/null || true

echo ""
echo "============================================"
echo "  ✅ HTTPS 证书已配置！"
echo "  域名: https://${DOMAIN}"
echo "  证书路径: /etc/letsencrypt/live/${DOMAIN}/"
echo "  证书将在到期前自动续期（certbot 每 12h 检查）"
echo "============================================"
