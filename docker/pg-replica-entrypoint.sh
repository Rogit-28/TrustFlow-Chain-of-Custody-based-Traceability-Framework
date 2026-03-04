#!/bin/sh
set -e

PGDATA=/var/lib/postgresql/data

# Ensure data dir owned by postgres user
mkdir -p "$PGDATA"
chown -R postgres:postgres "$PGDATA"
chmod 700 "$PGDATA"

# Only bootstrap if no data yet
if [ -z "$(ls -A "$PGDATA" 2>/dev/null)" ]; then
    echo "Bootstrapping replica from primary..."
    PGPASSWORD=repl_password gosu postgres pg_basebackup \
        -h db-primary \
        -p 5432 \
        -U repl_user \
        -D "$PGDATA" \
        -Fp -Xs -P -R \
        --slot=replica_slot_1

    # Append standby settings to auto.conf written by pg_basebackup -R
    cat >> "$PGDATA/postgresql.auto.conf" <<EOF
primary_conninfo = 'host=db-primary port=5432 user=repl_user password=repl_password application_name=trustdocs-replica'
primary_slot_name = 'replica_slot_1'
hot_standby = on
EOF
    touch "$PGDATA/standby.signal"
    chown postgres:postgres "$PGDATA/standby.signal"
    echo "Replica bootstrapped successfully."
else
    echo "Replica data directory already exists, starting normally."
fi

exec gosu postgres postgres -D "$PGDATA" \
  -c hot_standby=on \
  -c max_connections=100 \
  -c listen_addresses='*' \
  -c log_min_messages=warning
