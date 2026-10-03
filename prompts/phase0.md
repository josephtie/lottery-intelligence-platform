Tu es l'architecte principal, lead data engineer, lead machine-learning engineer et responsable qualité du projet.

Nous allons construire depuis zéro un nouveau système appelé :

LOTTERY INTELLIGENCE PLATFORM

IMPORTANT :

Ne réutilise pas l'architecture du précédent projet lottery-statistics-expert comme architecture cible.

Le précédent projet peut éventuellement servir de référence fonctionnelle pour identifier des fonctionnalités utiles, mais nous repartons sur une architecture propre.

Tu dois raisonner comme si aucune base SQLite, aucun schéma de données et aucun système de persistance n'existait.

==================================================
OBJECTIF
========

Construire une plateforme durable de collecte, conservation, validation, analyse statistique, expérimentation, backtesting, prédiction prospective, analyse de stratégies et mesure de rentabilité pour les jeux de loterie.

La plateforme doit devenir progressivement un actif de données et de recherche.

Elle ne doit pas être conçue comme un simple générateur de combinaisons.

==================================================
PRINCIPES
=========

1. DATA FIRST
2. REPRODUCIBILITY FIRST
3. NO DATA LOSS
4. NO DATA LEAKAGE
5. IMMUTABLE RAW DATA
6. VERSIONED DATASETS
7. VERSIONED MODELS
8. VERSIONED STRATEGIES
9. PROSPECTIVE EVALUATION
10. ECONOMIC EVALUATION
11. KNOWLEDGE RETENTION
12. FAIL SAFE

==================================================
ARCHITECTURE CIBLE
==================

Évaluer et proposer une architecture comprenant au minimum :

* PostgreSQL comme source de vérité ;
* object storage compatible S3/MinIO pour les données RAW ;
* Parquet pour les datasets analytiques ;
* DuckDB pour certaines analyses lourdes si pertinent ;
* Redis uniquement lorsque justifié ;
* Python pour data/research/ML ;
* API ;
* workers ;
* console web ;
* Hermes comme agent/orchestrateur.

Ne pas ajouter Kafka, Airflow, Spark ou Kubernetes simplement parce qu'ils sont populaires.

Toute infrastructure doit être justifiée par un besoin réel.

==================================================
LIVRABLE 1 — ARCHITECTURE
=========================

Produire :

docs/ARCHITECTURE.md

avec :

* architecture générale ;
* composants ;
* responsabilités ;
* flux de données ;
* flux d'expérimentation ;
* flux de prédiction ;
* flux de résultats ;
* sécurité ;
* sauvegarde ;
* observabilité ;
* stratégie de montée en charge.

Produire également :

docs/ARCHITECTURE_DECISIONS.md

sous forme d'ADR.

Chaque décision importante doit expliquer :

* problème ;
* options ;
* choix ;
* raisons ;
* conséquences.

==================================================
LIVRABLE 2 — ARBORESCENCE
=========================

Proposer une arborescence professionnelle du projet.

Séparer clairement :

* apps ;
* domain ;
* infrastructure ;
* collectors ;
* validation ;
* datasets ;
* research ;
* models ;
* strategies ;
* profitability ;
* knowledge ;
* tests ;
* docs ;
* deployment.

==================================================
LIVRABLE 3 — ROADMAP
====================

Produire une roadmap par étapes :

M0 Architecture
M1 Data Foundation
M2 Collection
M3 Validation
M4 Dataset/Snapshot
M5 Feature Engine
M6 Model Lab
M7 Turbo Lab
M8 Profitability Lab
M9 Prospective Engine
M10 Knowledge Engine
M11 API
M12 Console
M13 Production

Pour chaque étape préciser :

* objectifs ;
* livrables ;
* dépendances ;
* tests ;
* critères d'acceptation.

==================================================
RÈGLE DE TRAVAIL
================

NE CODE PAS immédiatement.

Commence par auditer les besoins fonctionnels déjà définis dans le contexte du projet.

Puis produis l'architecture.

Attends validation avant de commencer l'implémentation.

Ne fais aucune supposition silencieuse sur les règles de loterie.
Toute règle inconnue doit être configurable ou explicitement signalée.

==================================================
CRITÈRE DE RÉUSSITE
===================

À la fin de cette étape, nous devons disposer d'une architecture suffisamment précise pour qu'un autre développeur puisse commencer M1 sans devoir réinventer les décisions fondamentales.


Oui. Là, tu viens de donner une information **très importante pour l'architecture du registre des tirages** : le site expose non seulement les résultats, mais aussi un **planning des tirages à venir**, avec un `id`, un `eventId`, un nom, une date/heure et un `endDateTime`.

La page officielle Loto Bonheur affiche effectivement les tirages du jour et du lendemain, avec par exemple Soutra 09H55, Diamant 12H55, Moaye 15H55, etc. ([Loto bonheur][1]) La page officielle `/resultats` constitue parallèlement la source de consultation des résultats. ([Loto bonheur][2])

Donc je modifierais le Prompt 11 pour que **Loto Bonheur devienne explicitement la source externe primaire du Draw Registry**, avec deux flux distincts :

```text
              LOTO BONHEUR CI
                    │
        ┌───────────┴───────────┐
        │                       │
        ▼                       ▼
   PLANNING DES             RÉSULTATS
     TIRAGES                OFFICIELS
        │                       │
        ▼                       ▼
  DRAW SCHEDULE           DRAW RESULT
        │                       │
        └───────────┬───────────┘
                    ▼
              DRAW REGISTRY
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   PREDICTIONS  SETTLEMENT   RESEARCH
```

### Ajout spécifique au Prompt 11

# EXTENSION DU PROMPT 11

## SOURCES LOTO BONHEUR CI + REGISTRE DES TIRAGES

### 41. SOURCES EXTERNES OFFICIELLES

Pour la première implémentation de Loto Bonheur CI, utiliser comme sources externes primaires :

* site officiel : `https://lotobonheur.ci/`
* page officielle des résultats : `https://lotobonheur.ci/resultats`

La page d'accueil permet notamment d'identifier les tirages attendus et leurs horaires, tandis que `/resultats` constitue la source officielle de consultation des résultats. ([Loto bonheur][1])

NE PAS considérer le navigateur, le HTML rendu ou une réponse ponctuelle comme la base de données.

Le système doit identifier et documenter les endpoints/API réellement utilisés par le site.

---

# 42. DEUX COLLECTEURS DISTINCTS

Créer deux composants :

```text
lotobonheur_schedule_collector
lotobonheur_result_collector
```

### A. Schedule Collector

Responsable de la récupération des tirages :

```text
À VENIR
AUJOURD'HUI
DEMAIN
```

### B. Result Collector

Responsable de la récupération des résultats effectivement publiés.

Ne pas mélanger les deux responsabilités.

---

# 43. STRUCTURE DU PLANNING OBSERVÉE

Le système doit être capable de conserver les informations de planning de cette forme :

```json
{
  "drawGroups": [
    {
      "groupDate": "2026-10-03",
      "draws": [
        {
          "endDate": "Sam.12H55",
          "endDateTime": "2026-10-03T12:55:00Z",
          "endTime": "12H55",
          "eventId": "953",
          "id": "759367",
          "isSingleSet": false,
          "name": "Diamant",
          "preview": "Diamant - Sam.12H55"
        }
      ]
    }
  ],
  "drawsNumber": 11,
  "status": "0",
  "success": true
}
```

Cette structure doit être conservée dans le RAW original.

NE PAS transformer immédiatement cette réponse en quelques colonnes puis jeter le payload.

---

# 44. MAPPING DU TIRAGE

Créer une table de mapping permettant de relier :

```text
external_source
external_draw_id
external_event_id
game
draw_name
scheduled_date
scheduled_time
scheduled_datetime
timezone
source_payload_hash
```

Exemple :

```text
source              = lotobonheur.ci
external_draw_id    = 759367
external_event_id   = 953
draw_name           = Diamant
scheduled_date      = 2026-10-03
scheduled_time      = 12:55
scheduled_datetime  = 2026-10-03T12:55:00Z
```

Puis :

```text
external_draw_id
        ↓
draw_id interne
```

Ne jamais utiliser `759367` directement comme identifiant primaire interne.

---

# 45. ATTENTION À eventId ET id

Considérer :

```text
id
```

et :

```text
eventId
```

comme deux identifiants différents.

Ne jamais supposer qu'ils représentent la même chose.

Stocker séparément :

```text
external_draw_id
external_event_id
```

et déterminer expérimentalement leur stabilité dans le temps.

Créer un test :

```text
same draw over multiple collections
```

pour vérifier :

* `id` stable ;
* `eventId` stable ;
* nom stable ;
* horaire stable ;
* relation entre event et draw.

---

# 46. LE PLANNING DEVIENT UNE SOURCE DE VÉRITÉ POUR LES TIRAGES ATTENDUS

Lorsqu'un tirage apparaît dans le planning :

```text
DRAW SCHEDULED
```

créer ou mettre à jour :

```text
draw_registry
```

avec :

```text
status = SCHEDULED
```

Exemple :

```text
2026-10-03
12:55
Diamant
id=759367
eventId=953
```

devient un tirage attendu.

Le système sait donc qu'à partir du planning :

```text
DRAW EXPECTED
```

même si le résultat n'est pas encore disponible.

---

# 47. DÉTECTION DES TIRAGES MANQUANTS

C'est un point essentiel.

Si le planning indique :

```text
12:55 Diamant
```

mais qu'à 13:10 aucun résultat n'est disponible :

```text
SCHEDULED
      ↓
EXPECTED
      ↓
NO RESULT
      ↓
DELAYED
```

Après un délai configurable :

```text
MISSING_RESULT
```

Créer une alerte.

Ne jamais considérer automatiquement un tirage comme annulé simplement parce que le résultat n'est pas encore disponible.

---

# 48. COMPARAISON PLANNING ↔ RÉSULTAT

Lorsque le Result Collector récupère un résultat, effectuer le rapprochement :

```text
SCHEDULE RECORD
       +
RESULT RECORD
       ↓
DRAW REGISTRY
```

Vérifier :

```text
external_draw_id
external_event_id
draw_name
date
scheduled_time
actual_time
```

Créer un état :

```text
MATCHED
```

ou :

```text
PARTIAL_MATCH
```

ou :

```text
CONFLICT
```

---

# 49. NE PAS DÉDUIRE LE RÉSULTAT À PARTIR DU PLANNING

Le planning dit :

```text
"Diamant - Sam.12H55"
```

Il ne constitue PAS le résultat.

Il indique uniquement qu'un tirage est prévu.

Le résultat doit provenir de la source de résultats.

Architecture :

```text
SCHEDULE
    ≠
RESULT
```

Le registre doit conserver les deux.

---

# 50. HORAIRES ET TIMEZONE

Les données reçues peuvent contenir :

```text
2026-10-03T12:55:00Z
```

Le système doit conserver :

```text
source_datetime
source_timezone
normalized_datetime
normalized_timezone
```

Pour la Côte d'Ivoire :

```text
Africa/Abidjan
UTC+00:00
```

Ne jamais supprimer le `Z` original.

Ne jamais convertir silencieusement les timestamps.

---

# 51. SNAPSHOT DU PLANNING

À chaque collecte du planning, conserver un snapshot RAW :

```text
schedule_snapshot
```

Exemple :

```text
snapshot_id
source
collected_at
payload_hash
collector_version
draws_number
raw_object_id
```

Cela permet de répondre ultérieurement :

> Que disait exactement le site à 10h00 concernant les tirages du jour ?

---

# 52. HISTORIQUE DES CHANGEMENTS DE PROGRAMMATION

Le planning doit lui aussi être versionné.

Exemple :

```text
10:00
Diamant → 12H55

12:30
Diamant → 13H05
```

Ne pas écraser :

```text
12H55
```

Créer :

```text
schedule_version_1
schedule_version_2
```

avec :

```text
detected_at
old_value
new_value
source
reason
```

Cela permettra de détecter les changements de programmation.

---

# 53. COLLECTE INTELLIGENTE

Le schedule collector peut fonctionner plus fréquemment que nécessaire sans créer de doublons.

Exemple :

```cron
*/5 * * * *
```

À chaque exécution :

```text
fetch schedule
      ↓
hash payload
      ↓
hash déjà connu ?
   /        \
 YES        NO
  ↓          ↓
nothing    snapshot
```

Même si le contenu est identique, conserver éventuellement un `collection_event`, mais ne pas créer une nouvelle version logique inutile.

---

# 54. COLLECTE DES RÉSULTATS AUTOUR DU TIRAGE

Ne pas attendre uniquement l'heure exacte.

Pour un tirage prévu à :

```text
12:55
```

le système continue de vérifier :

```text
12:55
13:00
13:05
13:10
13:15
...
```

jusqu'à réception du résultat ou dépassement du délai configurable.

Le système doit donc fonctionner sur :

```text
expected_at
+
grace_period
+
retry_policy
```

et non sur un cron unique à 12:55.

---

# 55. DRAW REGISTRY FINAL

Le registre doit permettre d'obtenir une fiche comme :

```text
DRAW
────────────────────────────────────
Internal ID:
DRW-20261003-DIAMANT-759367

Game:
Loto Bonheur

Name:
Diamant

External draw ID:
759367

External event ID:
953

Scheduled:
2026-10-03 12:55 Africa/Abidjan

Source datetime:
2026-10-03T12:55:00Z

Actual result:
[...numbers...]

Status:
SETTLED

Schedule:
CONFIRMED

Result:
VALIDATED

Canonical version:
V1

Predictions:
12

Strategies:
5

Settlement:
COMPLETED

Anomalies:
NONE
```

---

# 56. CRITÈRE D'ACCEPTATION SPÉCIFIQUE LOTO BONHEUR

Le système doit réussir le scénario suivant :

```text
1. Le planning Loto Bonheur annonce un tirage.

2. Le système crée le tirage attendu dans DRAW REGISTRY.

3. Le système conserve la réponse RAW.

4. Une prédiction est générée pour ce draw_id.

5. La prédiction est LOCKED avant le tirage.

6. Le tirage arrive sur la source de résultats.

7. Le Result Collector le détecte.

8. Le résultat RAW est conservé.

9. Le résultat est validé.

10. Le résultat est associé au bon draw_id.

11. La version canonique est créée.

12. Les prédictions ciblant ce draw_id sont retrouvées.

13. Le settlement est effectué.

14. Turbo 2/3/4/5 sont calculés.

15. Les performances sont enregistrées.

16. Le knowledge engine reçoit le résultat.

17. L'ensemble est visible depuis DRAW REGISTRY.
```

---

# 57. OBJECTIF

Faire du **DRAW REGISTRY** la colonne vertébrale du système.

Le projet ne doit jamais raisonner simplement :

```text
"Voici les derniers numéros trouvés sur Internet."
```

Il doit raisonner :

```text
"Voici le tirage DRW-XXX,
prévu à telle date,
annoncé par telle source,
identifié par tel identifiant externe,
observé à telle heure,
avec tel RAW,
validé selon telle version,
frozen à tel moment,
ciblé par telles prédictions,
évalué par telles stratégies,
et ayant produit tel résultat."
```

C'est cette traçabilité qui permet ensuite de faire de la vraie recherche reproductible.

**Et je ferais une petite modification supplémentaire au projet :** le `draw_id` interne ne devrait pas être construit uniquement à partir du nom et de la date. Le système doit d'abord essayer de **faire correspondre l'identité externe `id + eventId + date + nom + heure`**, puis attribuer son propre UUID/ID interne. Ça évite qu'un changement de nom ou d'horaire du site casse l'historique.

Autre point intéressant dans tes données : **11 tirages sont annoncés sur les deux jours** (`6 + 5`), donc le Schedule Collector peut déjà construire une liste de tirages attendus avant même qu'un résultat existe. C'est exactement ce qu'il nous faut pour détecter les tirages manquants ou retardés.

[1]: https://lotobonheur.ci/ "Jouer en ligne | Loto Bonheur"
[2]: https://lotobonheur.ci/resultats "Résultats"
