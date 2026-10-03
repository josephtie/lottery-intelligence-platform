# Architecture Decision Records (ADR)

**Statut général : propositions à valider avant l’implémentation.** Les contraintes déjà exprimées dans les prompts sont indiquées comme telles ; les choix détaillés ci-dessous restent soumis à revue du propriétaire du projet.

## ADR-001 — Monolithe modulaire avant microservices

**Statut : proposé**

- **Contexte :** la plateforme comprend plusieurs domaines, mais commence avec un périmètre fonctionnel réduit et une équipe/opération d’exploitation limitée.
- **Options :** microservices par domaine ; monolithe modulaire ; scripts indépendants sans contrats communs.
- **Décision :** organiser un monolithe modulaire Python, avec frontières de domaine explicites. Exécuter API, workers et console comme processus/services séparés lorsque nécessaire, sans dupliquer les règles métier.
- **Raisons :** réduit les coûts de déploiement et les transactions distribuées tout en gardant une trajectoire d’extraction possible.
- **Conséquences :** contrats internes et tests d’architecture nécessaires ; extraction ultérieure seulement si un besoin de scaling, disponibilité ou isolation est démontré.

## ADR-002 — PostgreSQL comme source de vérité

**Statut : proposé, conforme aux exigences du projet**

- **Contexte :** les tirages, versions, expériences et règlements sont liés et nécessitent contraintes, transactions, concurrence et requêtes multi-utilisateurs.
- **Options :** SQLite ; PostgreSQL ; fichiers comme source principale.
- **Décision :** utiliser PostgreSQL pour l’état structuré canonique. Les fichiers ne sont que des artefacts RAW ou analytiques.
- **Raisons :** intégrité référentielle, transactions, contrôle d’accès et évolutivité opérationnelle.
- **Conséquences :** schéma et migrations versionnés ; sauvegarde/restauration PostgreSQL obligatoires. La version exacte du serveur sera épinglée avant l’implémentation.

## ADR-003 — RAW immuable dans un stockage objet compatible S3

**Statut : proposé, conforme aux exigences du projet**

- **Contexte :** une réponse source peut changer ou être corrigée ; les analyses doivent pouvoir retrouver exactement les données observées.
- **Options :** garder seulement le JSON normalisé en base ; fichiers locaux ; stockage objet S3-compatible.
- **Décision :** conserver les octets de chaque payload dans un stockage objet S3-compatible, indexé par SHA-256, et enregistrer ses métadonnées/provenance dans PostgreSQL.
- **Raisons :** séparation données brutes/données métier, déduplication par contenu et vérification d’intégrité.
- **Conséquences :** ordre d’écriture et reprise S3/PostgreSQL doivent gérer les objets orphelins ; aucune suppression automatique avant politique de rétention explicite.

## ADR-004 — Draw Registry séparant planning, résultat et versions

**Statut : proposé**

- **Contexte :** un tirage peut être annoncé avant la publication de son résultat, puis retardé, corrigé ou contesté. Les identifiants du fournisseur peuvent changer.
- **Options :** une table de résultats aplatie ; planning et résultats séparés sans registre ; registre interne versionné.
- **Décision :** créer un identifiant interne stable de tirage, des références externes par source, des observations de planning distinctes, des versions immuables de résultat et un pointeur explicite vers la version canonique.
- **Raisons :** permet d’identifier les tirages attendus/manquants, de rapprocher plusieurs sources, de préserver les corrections et de relier prédictions/datasets/settlements au bon tirage.
- **Conséquences :** les transitions d’état et changements de version sont audités ; une correction ne remplace pas rétroactivement les outcomes antérieurs.

## ADR-005 — Snapshots immuables pour la reproductibilité

**Statut : proposé, conforme aux exigences du projet**

- **Contexte :** l’historique évolue et une expérience doit rester reconstructible après ingestion de nouveaux tirages ou changement de règles.
- **Options :** requêter systématiquement l’état courant ; sauvegarder une copie complète par expérience ; snapshots manifestés.
- **Décision :** une expérience référence une version immuable de dataset/snapshot et les versions de features, modèle, stratégie, code, paramètres, seed et règles de paiement.
- **Raisons :** garantit que deux exécutions comparées utilisent les mêmes données et paramètres.
- **Conséquences :** un snapshot possède manifeste, cutoff, versions et hashes ; Parquet est un export dérivé, pas une source de vérité.

## ADR-006 — Prédictions verrouillées et résultats append-only

**Statut : proposé**

- **Contexte :** l’évaluation prospective n’est valide que si la prédiction est enregistrée avant le résultat et ne peut être modifiée silencieusement.
- **Options :** conserver les prédictions en fichiers ; modifier une prédiction avec un journal ; prédictions verrouillées et outcomes distincts.
- **Décision :** une prédiction référence un `target_draw_id`, est générée avant son cutoff, conserve candidats ordonnés et provenance, puis passe à un état verrouillé. Les évaluations et settlements sont des enregistrements séparés.
- **Raisons :** protège contre le look-ahead bias et rend toute correction auditable.
- **Conséquences :** les changements sont rejetés après verrouillage ; une correction du tirage entraîne un nouveau settlement versionné.

## ADR-007 — Gouvernance de recherche et niveaux d’évaluation explicites

**Statut : proposé, conforme aux exigences du projet**

- **Contexte :** essais multiples, sélection a posteriori et confusion entre hits, avantage prédictif et rentabilité peuvent produire des conclusions trompeuses.
- **Options :** métrique agrégée unique ; séparation des niveaux et protocole préenregistré.
- **Décision :** enregistrer hypothèses/protocoles avant examen confirmatoire, corriger les tests multiples quand indiqué, et distinguer `IN_SAMPLE`, `VALIDATION`, `WALK_FORWARD`, `OUT_OF_SAMPLE`, `PROSPECTIVE` et `REALIZED`.
- **Raisons :** les métriques restent interprétables et les résultats négatifs sont conservés.
- **Conséquences :** chaque conclusion inclut effectif, période, baseline, incertitude, version des données et limites ; « prometteur » ne signifie ni validé ni rentable.

## ADR-008 — Reporter Redis et les orchestrateurs distribués jusqu’à besoin démontré

**Statut : proposé**

- **Contexte :** Redis figure dans la vision cible, tandis que les prompts demandent de ne l’ajouter que si nécessaire et d’éviter les composants à la mode sans besoin.
- **Options :** Redis et file dès le premier déploiement ; broker/workflow distribué ; outbox/jobs PostgreSQL avec worker simple.
- **Décision :** commencer avec une outbox et des jobs persistés dans PostgreSQL, réservés de façon transactionnelle et idempotente. Reporter Redis, Kafka, Airflow, Spark et Kubernetes.
- **Raisons :** le volume initial ne justifie pas encore le coût opérationnel supplémentaire.
- **Conséquences :** mesurer latence, concurrence, reprises et débit ; ouvrir un ADR de remplacement si des seuils opérationnels sont dépassés.

## ADR-009 — Docker Compose pour le premier déploiement

**Statut : proposé, conforme aux exigences du projet**

- **Contexte :** la première cible est un déploiement maîtrisé sur un hôte/VPS, avec composants explicites et restauration testable.
- **Options :** Docker Compose ; Kubernetes ; déploiement natif par scripts.
- **Décision :** Docker Compose en V1, avec images épinglées, secrets hors Git, contrôles de santé, réseau isolé, backups et procédures de restauration.
- **Raisons :** adéquat au périmètre initial et plus simple à opérer.
- **Conséquences :** haute disponibilité et scaling horizontal avancé ne sont pas inclus d’emblée ; RPO/RTO devront être approuvés avant production.

## ADR-010 — Ancien projet conservé comme référence, import séparé et contrôlé

**Statut : proposé**

- **Contexte :** `lottery-statistics-expert-` contient une base SQLite, des scripts, des rapports et des expériences utiles, mais la nouvelle architecture doit repartir sur des fondations propres.
- **Options :** reprendre son schéma/code comme architecture ; ignorer entièrement les données existantes ; analyser et importer éventuellement par une procédure contrôlée.
- **Décision :** ne pas dépendre de son schéma ni importer automatiquement sa base. Utiliser le code et les rapports comme références fonctionnelles ; toute reprise de données sera un chantier séparé, en lecture seule à la source, avec validation, provenance, hashes, rapport de rejets et réconciliation.
- **Raisons :** protège l’architecture cible et évite de considérer les données historiques comme fiables sans audit.
- **Conséquences :** conserver l’ancien dépôt intact ; définir le périmètre de reprise et les règles de mapping avant toute migration.

## ADR-011 — API comme couche d’accès, pas comme moteur scientifique

**Statut : proposé, conforme aux exigences du projet**

- **Contexte :** la logique de collecte, scoring et recherche doit être testable/rejouable sans dépendre de l’interface.
- **Options :** logique métier dans les routes ; services de domaine appelés par l’API ; accès SQL depuis la console.
- **Décision :** exposer les cas d’usage par FastAPI et déléguer aux services/domaines ; refuser le SQL arbitraire et l’accès direct de la console à la base.
- **Raisons :** sépare interface, règles métier et accès aux données ; facilite tests et contrôle d’autorisation.
- **Conséquences :** contrats API versionnés, rôles à privilèges minimaux et tests d’intégration sur les cas d’usage.

## Conséquences globales et revue

Ces ADR décrivent une base de travail, pas une autorisation de mise en production. Les choix de fournisseur/hébergement, de sécurité, de rétention, de sauvegarde et de version exacte des dépendances restent à finaliser. Conformément à `prompts/phase0.md`, l’implémentation M1 commence après revue et validation de cette architecture.