#!/bin/bash
# certbot --manual-auth-hook for DuckDNS
# Usage: certbot ... --manual-auth-hook "/path/duckdns-auth.sh auth"
#        certbot ... --manual-cleanup-hook "/path/duckdns-auth.sh cleanup"
set -e

DUCKDNS_TOKEN="${DUCKDNS_TOKEN:?请设置 DUCKDNS_TOKEN 环境变量}"
DOMAIN="${CERTBOT_DOMAIN}"

# DuckDNS subdomains: strip .duckdns.org suffix
SUBDOMAIN="${DOMAIN%%.duckdns.org}"

if [ "$1" = "auth" ]; then
  echo ">>> DuckDNS TXT record: _acme-challenge.${DOMAIN} → ${CERTBOT_VALIDATION}"
  curl -s "https://www.duckdns.org/update?domains=${SUBDOMAIN}&token=${DUCKDNS_TOKEN}&txt=${CERTBOT_VALIDATION}"
  echo ""
  echo ">>> 等待 DNS 传播 (30s)..."
  sleep 30
elif [ "$1" = "cleanup" ]; then
  echo ">>> 清除 DuckDNS TXT record"
  curl -s "https://www.duckdns.org/update?domains=${SUBDOMAIN}&token=${DUCKDNS_TOKEN}&txt=removed&clear=true"
  echo ""
else
  echo "Usage: $0 {auth|cleanup}"
  exit 1
fi
