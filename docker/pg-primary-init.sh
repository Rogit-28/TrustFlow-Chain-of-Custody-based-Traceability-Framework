#!/bin/sh
set -e

# Create replication user and slot on primary
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$body\$
    BEGIN
      IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'repl_user') THEN
        CREATE USER repl_user WITH REPLICATION ENCRYPTED PASSWORD 'repl_password';
      END IF;
    END
    \$body\$;
EOSQL

# Create replication slot (idempotent)
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT pg_create_physical_replication_slot('replica_slot_1', true)
    WHERE NOT EXISTS (
      SELECT 1 FROM pg_replication_slots WHERE slot_name = 'replica_slot_1'
    );
EOSQL

# Allow replication connections (pg_hba.conf changes take effect immediately for new connections)
echo "host replication repl_user 0.0.0.0/0 scram-sha-256" >> "$PGDATA/pg_hba.conf"
echo "host all all 0.0.0.0/0 scram-sha-256" >> "$PGDATA/pg_hba.conf"

# Reload pg_hba.conf
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c "SELECT pg_reload_conf();"

echo "TrustDocs primary: replication user and slot created successfully."
