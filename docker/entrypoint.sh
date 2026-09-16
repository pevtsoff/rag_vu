#!/bin/bash
set -e

# Configure pg_textsearch in postgresql.conf
CONF_FILE="/var/lib/postgresql/data/postgresql.conf"
if [ -f "$CONF_FILE" ] && ! grep -q "shared_preload_libraries = 'pg_textsearch'" "$CONF_FILE"; then
    sed -i "s/^#shared_preload_libraries = ''/shared_preload_libraries = 'pg_textsearch'/" "$CONF_FILE"
    sed -i "s/^shared_preload_libraries = ''/shared_preload_libraries = 'pg_textsearch'/" "$CONF_FILE"
fi

# Run the original entrypoint
exec docker-entrypoint.sh postgres "$@"
