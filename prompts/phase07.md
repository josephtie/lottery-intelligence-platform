Tu es maintenant SRE / DevSecOps du LOTTERY INTELLIGENCE PLATFORM.

Préparer le système pour une exploitation durable sur VPS.

==================================================
OBJECTIFS
=========

Déployer :

PostgreSQL
MinIO
Redis si nécessaire
API
workers
console

avec Docker Compose dans un premier temps.

Ne pas utiliser Kubernetes sauf justification explicite.

==================================================
SÉCURITÉ

Mettre en place :

* secrets hors Git ;
* comptes DB séparés ;
* permissions minimales ;
* réseau Docker isolé ;
* TLS lorsque nécessaire ;
* authentification API ;
* audit ;
* rotation des secrets.

==================================================
BACKUP

PostgreSQL :

* backup quotidien ;
* rétention ;
* test de restauration.

MinIO :

* sauvegarde des RAW ;
* vérification d'intégrité.

==================================================
OBSERVABILITÉ

Logs structurés.

Metrics :

API
collector
database
workers
experiments
prediction jobs
storage.

==================================================
DISASTER RECOVERY

Documenter :

RPO
RTO
backup
restore
failure scenarios

Tester réellement une restauration.

==================================================
DEPLOYMENT

Créer :

docker-compose.yml
.env.example
deployment/
scripts/backup/
scripts/restore/
scripts/healthcheck/

Créer :

docs/OPERATIONS.md

Aucun déploiement n'est considéré terminé tant que la restauration n'a pas été testée.
