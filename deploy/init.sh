#!/usr/bin/env sh
set -eu

command -v openssl >/dev/null 2>&1 || { echo "需要 openssl" >&2; exit 1; }
umask 077
mkdir -p "$(dirname "$0")/secrets"

secret() {
  path="$(dirname "$0")/secrets/$1.txt"
  [ -f "$path" ] || openssl rand "$2" 32 >"$path"
}

secret master_key -base64
secret collector_token -hex
secret setup_token -hex
secret tdlib_database_key -hex

echo "Secrets 已生成。一次性 Setup Token："
cat "$(dirname "$0")/secrets/setup_token.txt"
echo
echo "启动：cd deploy && docker compose up -d"
