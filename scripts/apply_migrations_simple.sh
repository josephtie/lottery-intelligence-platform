#!/bin/bash
set -e

# Script pour appliquer les migrations sur le PostgreSQL local
# Utilise le socket Unix pour l'authentification locale
# Usage: ./scripts/apply_migrations_simple.sh

DB_NAME=${LOTTERY_DATABASE_NAME:-lottery_platform}
DB_USER=${LOTTERY_DATABASE_USER:-directus}
DB_PASSWORD=${LOTTERY_DATABASE_PASSWORD}

if [ -z "$DB_PASSWORD" ]; then
    echo "ERROR: LOTTERY_DATABASE_PASSWORD must be set in .env"
    exit 1
fi

echo "Applying migrations to local PostgreSQL..."
echo "Database: $DB_NAME"
echo "User: $DB_USER"
echo ""

# Find PostgreSQL socket directory
PG_SOCKET_DIR="/tmp"
if [ -d "/var/run/postgresql" ]; then
    PG_SOCKET_DIR="/var/run/postgresql"
fi

# Try different connection methods
echo "Attempting to connect to PostgreSQL..."

# Method 1: Try with postgres user via socket
if psql -h "$PG_SOCKET_DIR" -U postgres -c "SELECT 1" > /dev/null 2>&1; then
    echo "Connected via socket as postgres user"
    PSQL_CMD="psql -h $PG_SOCKET_DIR -U postgres"
elif psql -U postgres -c "SELECT 1" > /dev/null 2>&1; then
    echo "Connected as postgres user"
    PSQL_CMD="psql -U postgres"
else
    echo "ERROR: Cannot connect as postgres user without password"
    echo "Please run this script manually with the postgres password:"
    echo "  PGPASSWORD=<postgres_password> psql -h localhost -p 5432 -U postgres -c \"CREATE DATABASE $DB_NAME;\""
    echo "  PGPASSWORD=<postgres_password> psql -h localhost -p 5432 -U postgres -c \"CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';\""
    echo "  PGPASSWORD=<postgres_password> psql -h localhost -p 5432 -U postgres -c \"GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;\""
    echo "  PGPASSWORD=<postgres_password> psql -h localhost -p 5432 -U postgres -d $DB_NAME -c \"GRANT ALL ON SCHEMA public TO $DB_USER;\""
    echo "  PGPASSWORD=<postgres_password> psql -h localhost -p 5432 -U postgres -d $DB_NAME -c \"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $DB_USER;\""
    echo "  PGPASSWORD=<postgres_password> psql -h localhost -p 5432 -U postgres -d $DB_NAME -c \"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $DB_USER;\""
    echo ""
    echo "Then apply migrations:"
    echo "  export PGPASSWORD=<postgres_password>"
    echo "  for migration in infrastructure/postgres/migrations/*.sql; do"
    echo "    psql -h localhost -p 5432 -U postgres -d $DB_NAME -f \"\$migration\""
    echo "  done"
    exit 1
fi

# Check if database exists
echo "Checking if database exists..."
DB_EXISTS=$($PSQL_CMD -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" 2>/dev/null || echo "0")

if [ "$DB_EXISTS" = "0" ]; then
    echo "Creating database $DB_NAME..."
    $PSQL_CMD -c "CREATE DATABASE $DB_NAME;"
    echo "Database created."
else
    echo "Database $DB_NAME already exists."
fi

# Check if user exists
echo "Checking if user exists..."
USER_EXISTS=$($PSQL_CMD -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" 2>/dev/null || echo "0")

if [ "$USER_EXISTS" = "0" ]; then
    echo "Creating user $DB_USER..."
    $PSQL_CMD -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';"
    echo "User created."
else
    echo "User $DB_USER already exists."
fi

# Grant privileges
echo "Granting privileges..."
$PSQL_CMD -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
$PSQL_CMD -d $DB_NAME -c "GRANT ALL ON SCHEMA public TO $DB_USER;"
$PSQL_CMD -d $DB_NAME -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $DB_USER;"
$PSQL_CMD -d $DB_NAME -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $DB_USER;"
echo "Privileges granted."

# Apply migrations
echo ""
echo "Applying migrations..."
MIGRATIONS_DIR="$(cd "$(dirname "$0")/../infrastructure/postgres/migrations" && pwd)"

for migration in "$MIGRATIONS_DIR"/*.sql; do
    if [ -f "$migration" ]; then
        filename=$(basename "$migration")
        echo "Applying $filename..."
        $PSQL_CMD -d $DB_NAME -f "$migration" 2>&1 | grep -v "NOTICE:" || true
    fi
done

echo ""
echo "All migrations applied successfully!"
