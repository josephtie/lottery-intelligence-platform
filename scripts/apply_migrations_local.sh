#!/bin/bash
set -e

# Script pour appliquer les migrations sur le PostgreSQL local
# Utilise l'utilisateur directus configuré dans .env
# Usage: ./scripts/apply_migrations_local.sh

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

# Set PGPASSWORD for directus user
export PGPASSWORD=$DB_PASSWORD

# Use psql with directus user
PSQL_CMD="psql -h localhost -p 5432 -U $DB_USER"

# Check if user has access to database
echo "Checking access to database..."
if ! $PSQL_CMD -d $DB_NAME -c "SELECT 1" > /dev/null 2>&1; then
    echo "ERROR: User $DB_USER does not have access to database $DB_NAME."
    exit 1
fi

echo "Access OK."

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
