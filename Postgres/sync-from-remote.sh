#!/bin/sh
# Copia el esquema "public" de la base remota a la base local de desarrollo.
# La base remota solo se lee (pg_dump). La base local se BORRA y se recrea.
set -eu

: "${REMOTE_DATABASE_HOST:?Falta REMOTE_DATABASE_HOST en Postgres/.env}"
: "${REMOTE_DATABASE_NAME:?Falta REMOTE_DATABASE_NAME en Postgres/.env}"
: "${REMOTE_DATABASE_USER:?Falta REMOTE_DATABASE_USER en Postgres/.env}"
: "${REMOTE_DATABASE_PASSWORD:?Falta REMOTE_DATABASE_PASSWORD en Postgres/.env}"
: "${POSTGRES_DB:?Falta POSTGRES_DB en Postgres/.env}"
: "${POSTGRES_USER:?Falta POSTGRES_USER en Postgres/.env}"
: "${POSTGRES_PASSWORD:?Falta POSTGRES_PASSWORD en Postgres/.env}"

LOCAL_HOST="${LOCAL_DATABASE_HOST:-postgres}"
DUMP_FILE="/tmp/remote.dump"

case "$POSTGRES_DB" in
  *[!A-Za-z0-9_]*) echo "POSTGRES_DB solo admite letras, números y _" >&2; exit 1 ;;
esac
case "$POSTGRES_USER" in
  *[!A-Za-z0-9_]*) echo "POSTGRES_USER solo admite letras, números y _" >&2; exit 1 ;;
esac

echo "1/3 Descargando copia de la base remota (solo lectura)..."
PGPASSWORD="$REMOTE_DATABASE_PASSWORD" \
PGSSLMODE="${REMOTE_DATABASE_SSLMODE:-require}" \
pg_dump \
  --host "$REMOTE_DATABASE_HOST" \
  --port "${REMOTE_DATABASE_PORT:-5432}" \
  --username "$REMOTE_DATABASE_USER" \
  --dbname "$REMOTE_DATABASE_NAME" \
  --schema public \
  --format custom \
  --no-owner \
  --no-privileges \
  --file "$DUMP_FILE"

export PGPASSWORD="$POSTGRES_PASSWORD"
export PGSSLMODE=disable

echo "2/3 Recreando la base local '$POSTGRES_DB'..."
psql --host "$LOCAL_HOST" --username "$POSTGRES_USER" --dbname postgres \
  --set ON_ERROR_STOP=1 --quiet \
  --command "DROP DATABASE IF EXISTS \"$POSTGRES_DB\" WITH (FORCE);" \
  --command "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\";"

echo "3/3 Restaurando datos en la base local..."
# --clean --if-exists reemplaza el esquema public vacío si la copia lo incluye.
pg_restore \
  --host "$LOCAL_HOST" \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --clean --if-exists \
  --no-owner \
  --no-privileges \
  --exit-on-error \
  "$DUMP_FILE"

rm -f "$DUMP_FILE"
echo "Copia completada. Base local '$POSTGRES_DB' lista."
