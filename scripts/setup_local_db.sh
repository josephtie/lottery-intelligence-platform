#!/bin/bash
set -e

# Script pour configurer la base de données locale
# Usage: ./scripts/setup_local_db.sh

echo "Configuration de la base de données locale PostgreSQL..."
echo ""
echo "Ce script va:"
echo "  - Créer la base de données lottery_platform"
echo "  - Créer l'utilisateur directus"
echo "  - Appliquer les 26 migrations"
echo ""
echo "Vous devez fournir le mot de passe de l'utilisateur postgres."
echo ""

# Read postgres password
read -s -p "Mot de passe postgres: " PGPASSWORD
echo ""
export PGPASSWORD

# Execute setup SQL
echo "Exécution du script de configuration..."
cd /Users/macbookpro2019/IdeaProjects/lottery-intelligence-platform
psql -h localhost -p 5432 -U postgres -f scripts/setup_local_db.sql

echo ""
echo "✅ Configuration terminée avec succès !"
echo ""
echo "L'API Docker peut maintenant se connecter à votre PostgreSQL local."
