#!/bin/bash
set -e

# Script pour appliquer les migrations sur le PostgreSQL local
# Doit être exécuté en tant qu'utilisateur système postgres
# Usage: sudo -u postgres ./scripts/apply_migrations_as_postgres.sh

DB_NAME=${LOTTERY_DATABASE_NAME:-lottery_platform}
DB_USER=${LOTTERY_DATABASE_USER:-directus}
DB_PASSWORD=${LOTTERY_DATABASE_PASSWORD}

if [ -z "$DB_PASSWORD" ]; then
    echo "ERROR: LOTTERY_DATABASE_PASSWORD must be set in .env"
    exit 1
fi

echo "Applying migrations to local PostgreSQL as postgres user..."
echo "Database: $DB_NAME"
echo "User: $DB_USER"
echo ""

# Use psql without host (Unix socket)
PSQL_CMD="psql"

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
