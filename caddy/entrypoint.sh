#!/bin/sh
set -e

# Hash the plaintext password for Caddy basicauth
export ADMIN_USER="${ADMIN_USER:-admin}"
export ADMIN_HASH=$(caddy hash-password --plaintext "${ADMIN_PASS:-admin}")

exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
