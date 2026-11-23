-- Setup script for local PostgreSQL database (user creation only)
-- Usage: PGPASSWORD=<postgres_password> psql -h localhost -p 5432 -U postgres -f scripts/setup_local_db.sql

-- Create database if not exists
SELECT 'CREATE DATABASE lottery_platform'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'lottery_platform')
\gexec

-- Create user if not exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'directus') THEN
        CREATE USER directus WITH PASSWORD 'directus';
    END IF;
END
$$;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE lottery_platform TO directus;

-- Connect to lottery_platform
\c lottery_platform

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO directus;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO directus;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO directus;

-- Display completion message
SELECT 'Database and user setup completed successfully!' AS status;
SELECT 'Now run: ./scripts/apply_migrations_local.sh' AS next_step;
