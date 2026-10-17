#!/bin/bash
set -e

# Get environment variables
DB_NAME=${LOTTERY_DATABASE_NAME:-lottery_platform}
DB_USER=${LOTTERY_DATABASE_USER:-directus}
DB_PASSWORD=${LOTTERY_DATABASE_PASSWORD}

if [ -z "$DB_PASSWORD" ]; then
    echo "ERROR: LOTTERY_DATABASE_PASSWORD must be set"
    exit 1
fi

echo "Creating database and user..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Create user if not exists
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '$DB_USER') THEN
            CREATE ROLE $DB_USER WITH LOGIN PASSWORD '$DB_PASSWORD';
        END IF;
    END
    \$\$;

    -- Create database if not exists
    SELECT 'CREATE DATABASE $DB_NAME'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DB_NAME')\gexec

    -- Grant privileges on database
    GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
EOSQL

echo "Database and user created successfully."

# Grant schema privileges (must be done after database exists)
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$DB_NAME" <<-EOSQL
    -- Grant schema privileges
    GRANT ALL ON SCHEMA public TO $DB_USER;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $DB_USER;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $DB_USER;
EOSQL

echo "Schema privileges granted."

# Apply migrations if they exist (using postgres superuser)
if [ -d "/docker-entrypoint-initdb.d/migrations" ]; then
    echo "Applying database migrations..."
    for migration in /docker-entrypoint-initdb.d/migrations/*.sql; do
        if [ -f "$migration" ]; then
            echo "Applying $(basename "$migration")..."
            psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$DB_NAME" -f "$migration"
        fi
    done
    echo "Migrations applied successfully."
fi
