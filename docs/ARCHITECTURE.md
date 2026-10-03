# Architecture — Lottery Intelligence Platform

**Statut : proposition d’architecture à valider avant implémentation.**  
**Périmètre initial :** Loto Bonheur CI, avec un modèle de domaine extensible à d’autres jeux.

## 1. Objectifs et contraintes

La plateforme est un système de données et de recherche reproductible, pas un générateur de combinaisons ni une promesse de gains. Elle doit conserver la provenance des informations, empêcher les fuites temporelles, versionner les expériences et distinguer les résultats statistiques des résultats économiques.

Principes directeurs :

- PostgreSQL est la source de vérité structurée.
- Les réponses sources RAW sont conservées octet pour octet dans un stockage objet, adressées par contenu et jamais écrasées.
- Les tirages, règles, datasets, modèles, stratégies, prédictions et résultats ont des identifiants et versions explicites.
- Une correction ajoute une version et un événement d’audit ; elle ne réécrit pas silencieusement l’historique.
- Les évaluations `IN_SAMPLE`, `VALIDATION`, `WALK_FORWARD`, `OUT_OF_SAMPLE`, `PROSPECTIVE` et `REALIZED` restent séparées.
- Toute décision statistique doit inclure période, effectif, protocole, limites et correction des tests multiples lorsque pertinente.
- Aucun composant ne peut déclarer un avantage économique sans protocole et preuve prospective appropriés.

## 2. Architecture logique

```text
Sources officielles
  ├── Schedule Collector ──┐
  └── Result Collector ────┴──> RAW Object Storage (S3/MinIO)
                                      │ hash + provenance
                                      ▼
                         Ingestion / Validation / Reconciliation
                                      │
                                      ▼
                            PostgreSQL — source de vérité
                              ├── Draw Registry
                              ├── Dataset & Snapshot Registry
                              ├── Prediction & Settlement
                              ├── Research Ledger
                              ├── Strategy & Profitability
                              └── Knowledge Ledger
                                      │
                              Domain / Research services
                               ├── Python workers
                               ├── Parquet exports
                               └── DuckDB analytics (au besoin)
                                      │
                         FastAPI — couche d’accès, sans logique scientifique
                              ├── Console web
                              └── Hermes via interfaces contrôlées
```

La V1 est un **monolithe modulaire** exécuté dans des processus séparés (API, workers, console) et déployé avec Docker Compose. Les frontières sont des modules et contrats internes ; des microservices ne seront extraits qu’en présence d’un besoin opérationnel mesuré.

## 3. Composants et responsabilités

### 3.1 Catalogue de jeux et de règles

Le catalogue décrit chaque jeu, sa version de règles, ses types de tirage, univers de numéros, nombre de numéros, ordre, timezone, cadence et règles de paiement. Les changements de règles créent une nouvelle version avec une période d’effet. Aucune règle inconnue n’est supposée : elle est marquée à confirmer et empêche le scoring concerné.

### 3.2 Collecteurs

Les collecteurs sont séparés par responsabilité et adaptés à une source :

- le **Schedule Collector** observe les tirages annoncés et leurs changements ;
- le **Result Collector** observe les résultats réellement publiés ;
- chaque exécution crée un `collection_run` et des événements, même si le payload est déjà connu ;
- les réponses HTTP, statuts, en-têtes utiles, URL/source, heures de collecte, version de collecteur et hash sont enregistrés ;
- les retries sont bornés, temporisés et idempotents.

Une collecte de planning ne constitue jamais un résultat de tirage. Le système conserve le payload brut avant toute transformation.

### 3.3 Stockage RAW et ingestion

Le stockage objet S3-compatible (MinIO en déploiement initial si retenu) conserve les octets originaux sous une clé dérivée du SHA-256. Les métadonnées résident dans PostgreSQL. Un contenu identique peut référencer le même objet RAW, mais chaque observation reste traçable par un événement de collecte.

Il n’existe pas de transaction distribuée entre PostgreSQL et S3 : l’objet est écrit et vérifié avant la transaction de métadonnées. Les objets orphelins sont détectés par un contrôle de cohérence ; aucune purge automatique n’est effectuée sans politique de rétention validée.

### 3.4 Validation et réconciliation

Les contrôles sont enregistrés par exécution et couvrent : schéma, types, règles du jeu, plage et unicité des numéros, date/heure, séquence attendue, complétude et cohérence entre sources. Un conflit produit une anomalie explicite et bloque le choix canonique automatique. Une validation réussie n’efface pas les erreurs et avertissements observés.

### 3.5 Draw Registry

Le registre des tirages est la référence canonique pour les tirages attendus, observés, validés et réglés.

- `draw_id` est un identifiant interne stable, jamais l’identifiant fourni par une source.
- Les identifiants externes (`external_draw_id`, `external_event_id`) sont conservés séparément et associés à la source.
- L’identité logique s’appuie sur jeu/version de règles, type de tirage et séquence/heure programmée ; les identifiants externes servent à la réconciliation, sans être présumés stables avant vérification.
- Planning et résultat sont des enregistrements distincts reliés au même tirage lorsqu’ils concordent.
- Chaque observation validée crée une `draw_version` immuable ; le registre indique la version canonique courante sans supprimer les précédentes.
- Une correction, un conflit ou un changement de programmation produit un événement/version avec source, heure, raison et valeurs avant/après.
- Les heures originales et timezone source sont conservées ; les instants normalisés sont stockés en UTC avec l’identifiant de timezone applicable.

Cycle nominal : `SCHEDULED → EXPECTED → COLLECTING → DETECTED → VALIDATING → VALIDATED → CONFIRMED → FROZEN → SETTLED`. Les états exceptionnels incluent notamment `DELAYED`, `MISSING`, `INVALID`, `CONFLICT`, `CORRECTED`, `CANCELLED` et `DISPUTED`. Les transitions sont contrôlées et auditées.

### 3.6 PostgreSQL — domaines logiques

Schémas logiques proposés (à détailler en ADR/migrations avant M1) :

- `catalog` : jeux, versions, types de tirages, règles de paiement ;
- `ingestion` : sources, collectes, objets RAW, validations et événements ;
- `core` : Draw Registry, versions de tirage, numéros ordonnés, corrections ;
- `datasets` : datasets, versions, membres et snapshots ;
- `research` : features, hypothèses, expériences, exécutions et métriques ;
- `models` : registre et versions de modèles ;
- `prediction` : exécutions, candidats classés, verrous et outcomes ;
- `strategy` / `finance` : stratégies versionnées, tickets, stakes, paiements, bankrolls et settlements ;
- `knowledge` : findings, conclusions, limites et liens vers expériences ;
- `ops` : jobs, outbox, audit et état opérationnel.

Les identifiants utilisent des clés internes stables ; les contraintes d’unicité et clés étrangères expriment les invariants métier. Les migrations de schéma sont versionnées et testées.

### 3.7 Datasets, features et recherche

Un snapshot de dataset est immuable et identifie précisément les versions de tirages canoniques incluses, la coupure temporelle, le schéma, les règles, la version de code, la définition des features et leurs checksums. Deux exécutions déclarées reproductibles utilisent le même snapshot, mêmes versions, paramètres et seed.

Les exports Parquet sont des artefacts dérivés, non une source de vérité. Chaque export inclut un manifeste vérifiable. DuckDB est utilisé pour des analyses locales ou batch lorsqu’il apporte un avantage mesuré ; PostgreSQL reste le registre transactionnel.

Toute feature à l’instant `t` ne dépend que d’informations effectivement disponibles avant `t`. Les tests anti-leakage sont obligatoires. Les résultats de recherche indiquent leur niveau d’évaluation et ne sont jamais agrégés entre niveaux sans explicitation.

### 3.8 Prédictions, règlement et rentabilité

Une prédiction référence directement `target_draw_id`, le snapshot, les versions de modèle/feature/stratégie, paramètres, seed, candidats ordonnés, scores, génération et coupure. Elle est verrouillée avant l’échéance définie par la version du jeu. Après verrouillage, sa mutation est rejetée et auditée.

Après validation et gel d’un résultat, le settlement crée un outcome distinct. Une correction de résultat conduit à une nouvelle version de settlement ; l’ancien calcul reste consultable. Les règles de paiement, mises et conversions monétaires sont versionnées avec leur source et leur période d’effet.

Les mesures de simulation/backtest, OOS, prospective et résultats réalisés sont identifiées séparément. Les métriques minimales comprennent mises, paiements bruts, profit net, ROI, drawdown, séries de pertes et effectif. Un résultat statistique positif ne suffit pas à déclarer une stratégie rentable.

### 3.9 Research Ledger et Knowledge Ledger

Une hypothèse est enregistrée avant l’analyse confirmatoire. Chaque exécution référence les données, features, modèle, stratégie, code, configuration, seed et protocole. Les conclusions négatives et limitations sont conservées au même titre que les résultats positifs. La détection d’expériences similaires aide à éviter les répétitions non justifiées, sans bloquer l’exploration documentée.

### 3.10 API, console et Hermes

FastAPI expose les opérations de consultation et commandes métier explicites. L’API valide les accès et délègue aux services ; elle ne contient pas l’algorithme statistique principal. Les réponses exposent provenance, statut, niveau d’évaluation et fraîcheur.

La console présente la santé des données, tirages et versions, datasets, expériences, modèles, prédictions, settlements, rentabilité et connaissances. Les catégories `historical`, `simulated`, `OOS`, `prospective` et `realized` sont visuellement distinctes.

Hermes agit comme orchestrateur via API/CLI contrôlées. Il ne reçoit pas un accès SQL général et ne peut pas modifier directement une prédiction verrouillée ou une conclusion auditée.

## 4. Flux principaux

### 4.1 Publication du planning

1. Le Schedule Collector conserve chaque payload brut et son empreinte.
2. Le validateur normalise les événements sans jeter les champs source.
3. Les observations de planning créent ou versionnent les tirages attendus.
4. Les changements d’heure/nom sont historisés et les tirages en retard déclenchent une anomalie après un délai configurable.

### 4.2 Résultat et gel

1. Le Result Collector capture le payload source dans RAW.
2. Le rapprochement associe le résultat à un tirage attendu ou crée un candidat à réconcilier.
3. Les validateurs vérifient structure, règles et sources secondaires disponibles.
4. En cas de conflit, le résultat est mis en quarantaine logique ; aucun choix silencieux n’est fait.
5. Une version validée est confirmée puis gelée. Toute prédiction est réglée par référence à `draw_id` et `draw_version_id`.
6. L’outbox PostgreSQL publie les tâches downstream de façon récupérable et idempotente.

### 4.3 Expérience de recherche

`hypothèse préenregistrée → protocole → snapshot → features versionnées → modèle/stratégie versionnés → exécution → métriques séparées → contrôles statistiques → finding avec limites`.

### 4.4 Cycle prospectif

`tirage attendu → génération avant cutoff → prédiction verrouillée → tirage validé/gelé → outcome/settlement append-only → métriques prospectives → knowledge record`.

## 5. Exécution et infrastructure

- Déploiement de départ : Docker Compose sur un hôte Linux/VPS, environnements dev/test/prod séparés.
- Services initiaux : PostgreSQL, stockage S3-compatible, API, worker(s), console et proxy TLS selon le contexte de déploiement.
- Redis n’est pas requis au démarrage. Les tâches asynchrones initiales peuvent utiliser une table PostgreSQL d’outbox/jobs avec réservation transactionnelle et reprise. Redis n’est ajouté que si la mesure de charge/latence justifie cache, file dédiée ou coordination.
- Aucun Kubernetes, Kafka, Airflow ou Spark en V1 sans besoin et ADR dédiés.
- Les versions d’images et dépendances sont fixées ; pas de tag flottant en production.

## 6. Sécurité et confidentialité

- Secrets hors Git, injectés au déploiement via gestionnaire approprié ou fichiers secrets protégés.
- Comptes PostgreSQL séparés par service, droits minimaux ; migrations avec rôle distinct du rôle runtime.
- Réseau interne isolé ; seuls les points d’entrée nécessaires sont exposés.
- Authentification et autorisation API explicites, TLS en dehors du réseau privé, CORS limité aux origines nécessaires.
- Audit des changements de règles, corrections, transitions d’état, verrous et settlements.
- Aucun endpoint de SQL arbitraire, shell, écriture générique ou export non borné.
- Les payloads et logs sont contrôlés pour éviter secrets, données sensibles ou contenu non nécessaire.

## 7. Observabilité et reprise

Chaque traitement possède `correlation_id`, `collection_run_id` ou `experiment_run_id`, états, timestamps, tentatives et erreurs structurées. Les métriques suivent au minimum : taux de succès de collecte, retard des résultats attendus, erreurs de validation, conflits, fraîcheur des données, jobs en attente/échec, latence API, capacité PostgreSQL et stockage RAW.

Les sauvegardes couvrent PostgreSQL et les objets RAW, avec manifeste/checksum et tests réguliers de restauration. Les objectifs RPO/RTO sont à fixer avec l’environnement d’exploitation avant production. Une sauvegarde non restaurée en test n’est pas considérée vérifiée.

## 8. Tests et critères d’acceptation de l’architecture

Avant la production, démontrer par tests automatisés et exercices de reprise :

1. Un payload identique répété ne crée pas de nouvel objet logique, mais conserve les événements de collecte.
2. Un payload corrigé crée une nouvelle version sans effacer le RAW ni l’historique antérieur.
3. Un tirage planifié sans résultat devient retardé/manquant selon la politique, jamais annulé implicitement.
4. Un conflit de sources empêche le gel automatique.
5. Un snapshot peut être réexporté avec le même manifeste et les mêmes hashes.
6. Une feature ne lit aucune observation postérieure à sa coupure.
7. Une prédiction verrouillée ne peut être modifiée ; le résultat la référence par identifiant de tirage.
8. Une correction de tirage crée un nouveau settlement, sans écraser l’ancien.
9. Les métriques par niveau d’évaluation ne sont pas mélangées.
10. Une restauration PostgreSQL + RAW reproduit les données et leurs liens de provenance.

## 9. Décisions à confirmer avant M1

- Hôte, stockage et politique de sauvegarde de production (RPO/RTO, rétention, chiffrement).
- Méthode d’authentification et utilisateurs de la console/API.
- Détails confirmés des endpoints officiels Loto Bonheur, stabilité des identifiants externes et politique de collecte.
- Sources officielles et dates d’effet pour chaque règle de jeu et de paiement.
- Périmètre et protocole d’une éventuelle importation contrôlée depuis l’ancien projet SQLite.
- Version majeure PostgreSQL, version Python et politique de mise à jour, à figer dans l’environnement de build.

Ces points ne bloquent pas le modèle logique, mais empêchent de déclarer une configuration de production finalisée.