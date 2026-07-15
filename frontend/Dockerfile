# ==== Stage 1: Build ====
FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

# ==== Stage 2: Serve ====
FROM nginx:alpine

# openssl: self-signed cert generation (IP-only mode)
# envsubst: nginx config template substitution
RUN apk add --no-cache openssl

COPY --from=builder /app/dist /usr/share/nginx/html

# nginx config uses envsubst for ${DOMAIN} substitution
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 80 443
ENTRYPOINT ["/docker-entrypoint.sh"]
