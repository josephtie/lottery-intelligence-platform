Tu es maintenant lead Data Engineer du projet LOTTERY INTELLIGENCE PLATFORM.

Ne travaille pas encore sur les modèles prédictifs.

Ta mission est de construire le DATA FOUNDATION.

==================================================
OBJECTIF
========

Créer une infrastructure de données capable de conserver pendant plusieurs années :

* tirages ;
* jeux ;
* règles ;
* sources ;
* réponses API originales ;
* fichiers ;
* corrections ;
* validations ;
* snapshots ;
* provenance ;
* versions.

Aucune donnée historique ne doit pouvoir être perdue par une opération normale.

==================================================
STOCKAGE
========

Utiliser :

POSTGRESQL comme source de vérité structurée.

MINIO/S3 comme stockage RAW immutable.

PARQUET comme format de dataset analytique.

Ne pas utiliser SQLite.

Ne pas utiliser CSV comme source de vérité.

==================================================
RAW DATA
========

Chaque collecte doit conserver la réponse originale.

Créer un système de :

source
collection_run
raw_object
content_hash
metadata

Un objet RAW doit être identifié par un hash cryptographique.

Si exactement le même contenu est reçu deux fois, le système doit le reconnaître.

Si le contenu change, les deux versions doivent être conservées.

==================================================
SCHÉMA
======

Concevoir au minimum :

catalog.games
catalog.game_versions
catalog.draw_types
catalog.payout_rules
catalog.payout_rule_versions

ingestion.sources
ingestion.collection_runs
ingestion.raw_objects
ingestion.ingestion_events
ingestion.validation_events

core.draws
core.draw_numbers
core.draw_corrections

datasets.datasets
datasets.dataset_versions
datasets.dataset_members

Chaque table doit avoir une justification.

==================================================
IMMUTABILITÉ
============

Les données RAW sont immuables.

Les tirages validés doivent avoir une identité stable.

Une correction ne doit pas écraser silencieusement l'information précédente.

Créer un mécanisme de correction/version.

==================================================
PROVENANCE
==========

Pour tout tirage, pouvoir retrouver :

draw
→ validation
→ ingestion run
→ source
→ raw object
→ hash

Pour tout dataset :

dataset
→ version
→ tirages inclus
→ date de création
→ code version
→ schema version
→ hash.

==================================================
DATASET SNAPSHOT
================

Créer un mécanisme permettant :

create_dataset_snapshot()

Chaque snapshot doit être immuable.

Deux expériences utilisant le même snapshot doivent utiliser exactement les mêmes données.

Créer également :

compare_dataset_versions()

==================================================
PARQUET
=======

Créer un export reproductible :

dataset_version → Parquet

Le fichier doit contenir suffisamment de métadonnées pour retrouver :

* dataset version ;
* génération ;
* hash ;
* schema version.

==================================================
BACKUP
======

Prévoir :

* backup PostgreSQL ;
* backup MinIO ;
* vérification de restauration ;
* procédure de recovery.

Créer :

docs/DATA_RECOVERY.md

==================================================
TESTS
=====

Créer des tests pour :

* doublons ;
* hash ;
* intégrité référentielle ;
* correction ;
* snapshot ;
* reproductibilité ;
* restauration ;
* corruption ;
* données manquantes ;
* dates incohérentes.

==================================================
CRITÈRE D'ACCEPTATION

Je dois pouvoir :

1. collecter un tirage ;
2. retrouver sa réponse RAW exacte ;
3. valider le tirage ;
4. créer un dataset version ;
5. créer un snapshot ;
6. exporter ce snapshot en Parquet ;
7. supprimer le container applicatif ;
8. restaurer PostgreSQL et MinIO ;
9. retrouver exactement les mêmes données.

Ne commence aucune fonctionnalité ML avant que ces critères soient validés.
