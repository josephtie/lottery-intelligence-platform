# AJOUT MAJEUR — VRAI REGISTRE DES TIRAGES

## 22. DRAW REGISTRY — REGISTRE CENTRAL ET IMMUTABLE DES TIRAGES

Construire un véritable **Draw Registry** (`draw_registry`) qui constitue le registre canonique de tous les tirages connus par le système.

Ce registre ne doit pas être une simple liste de résultats.

Il doit permettre de répondre de manière déterministe :

* quel tirage est-ce ?
* quel jeu ?
* quelle variante ?
* quelle date ?
* quelle heure prévue ?
* quelle heure réelle ?
* quelle source l'a fourni ?
* quand a-t-il été collecté ?
* quel payload RAW correspond à ce tirage ?
* quelle version du résultat est actuellement validée ?
* quelles sources le confirment ?
* quelles anomalies ont été détectées ?
* quelles prédictions ciblaient ce tirage ?
* quelles stratégies étaient actives ?
* quand le tirage a-t-il été déclaré officiel ?
* quand le settlement a-t-il été effectué ?
* le tirage est-il complet ?
* le tirage est-il corrigé ?
* le tirage est-il contesté ?
* quelle version doit être utilisée pour la recherche ?

---

# 23. IDENTITÉ CANONIQUE DU TIRAGE

Ne jamais utiliser uniquement un timestamp ou un numéro de tirage fourni par une source externe comme identité interne.

Créer un identifiant interne stable :

```text
draw_id
```

L'identité logique doit être déterminée par une combinaison contrôlée de :

```text
game_id
game_version_id
draw_type_id
scheduled_date
scheduled_sequence
```

Lorsque la source fournit un identifiant externe :

```text
external_draw_id
```

le conserver séparément.

Exemple :

```text
draw_id:
DRW_01J...

game:
LOTO_BONHEUR

game_version:
v2026.01

draw_type:
STANDARD

scheduled_date:
2026-10-03

scheduled_sequence:
03

external_draw_id:
SOURCE_874521
```

Ne jamais confondre :

```text
draw_id
```

avec :

```text
external_draw_id
```

---

# 24. ÉTATS DU TIRAGE

Le registre doit gérer un véritable cycle de vie :

```text
SCHEDULED
    ↓
EXPECTED
    ↓
COLLECTING
    ↓
DETECTED
    ↓
VALIDATING
    ↓
VALIDATED
    ↓
CONFIRMED
    ↓
FROZEN
    ↓
SETTLED
```

Et les états exceptionnels :

```text
MISSING
DELAYED
INVALID
CONFLICT
CORRECTED
CANCELLED
DISPUTED
SUPERSEDED
```

Les transitions doivent être contrôlées.

Exemple :

```text
FROZEN
```

ne peut pas devenir silencieusement :

```text
VALIDATED
```

Une correction doit créer une nouvelle version et un événement d'audit.

---

# 25. REGISTRE DES VERSIONS DU TIRAGE

Séparer :

```text
draw
```

de :

```text
draw_version
```

Un tirage peut avoir plusieurs versions documentées :

```text
DRAW
 ├── VERSION 1 — source initiale
 ├── VERSION 2 — confirmation
 └── VERSION 3 — correction officielle
```

Chaque version doit contenir :

```text
draw_version_id
draw_id
version_number
winning_numbers
draw_date
draw_time
source_id
raw_object_id
payload_hash
schema_version
collected_at
validated_at
confirmed_at
created_at
created_by
status
correction_reason
```

Une version ne doit jamais être supprimée.

---

# 26. SNAPSHOT CANONIQUE

Le registre doit désigner explicitement une version :

```text
canonical_version_id
```

Cette version représente le résultat actuellement reconnu comme canonique par le système.

Mais conserver toutes les versions historiques.

Exemple :

```text
DRAW-123

v1
  source A
  10:05
  résultat X

v2
  source B
  10:08
  résultat X

v3
  source officielle
  12:30
  résultat Y

canonical = v3
```

Ne jamais écraser v1 ou v2.

---

# 27. DRAW NUMBERS

Ne pas stocker uniquement les numéros dans un champ texte ou JSON.

Créer une structure :

```text
draw_numbers
```

avec au minimum :

```text
draw_version_id
position
number
number_role
```

Exemple :

```text
position | number | role
---------|--------|---------
1        | 07     | WINNING
2        | 23     | WINNING
3        | 41     | WINNING
4        | 56     | WINNING
5        | 72     | WINNING
```

Cela permettra ultérieurement d'analyser :

* position ;
* ordre ;
* fréquence ;
* retard ;
* co-occurrence ;
* top-K ;
* Turbo ;
* séquences.

Ne jamais perdre l'information de position si elle existe dans les règles officielles.

---

# 28. DRAW SCHEDULE REGISTRY

Créer également un registre des tirages attendus :

```text
draw_schedule
```

Il doit permettre de connaître les tirages qui **devraient exister**, même lorsqu'ils n'ont pas encore été collectés.

Champs :

```text
schedule_id
game_id
game_version_id
draw_type_id
scheduled_date
scheduled_time
timezone
sequence
expected
status
```

Cela permet de détecter :

```text
EXPECTED DRAW
       ↓
NO RESULT
       ↓
MISSING / DELAYED
```

et pas uniquement :

```text
dernier résultat connu
```

C'est essentiel pour détecter les trous historiques.

---

# 29. DRAW ↔ PREDICTION

Chaque prédiction doit référencer directement :

```text
target_draw_id
```

et non seulement :

```text
target_date
```

Ainsi :

```text
Prediction P123
        ↓
Draw DRW456
        ↓
Draw Version DV456-2
```

Le système doit pouvoir retrouver toutes les prédictions associées à un tirage.

---

# 30. DRAW ↔ DATASET

Chaque dataset doit pouvoir indiquer précisément :

```text
latest_draw_id
```

et :

```text
latest_draw_version_id
```

Une expérimentation doit donc pouvoir être reconstruite :

```text
Experiment
    ↓
Dataset Snapshot
    ↓
Draw Registry
    ↓
Draw Version
    ↓
RAW Object
```

---

# 31. DRAW ↔ SETTLEMENT

Le settlement doit être attaché au :

```text
draw_id
```

et à la :

```text
canonical_draw_version_id
```

Ainsi, si le résultat officiel est corrigé ultérieurement, le système peut détecter :

```text
PREVIOUS SETTLEMENT
        ↓
CANONICAL VERSION CHANGED
        ↓
RE-SETTLEMENT REQUIRED
```

Mais **jamais automatiquement écraser l'ancien settlement**.

Créer un nouveau settlement/version :

```text
settlement_version
```

avec la raison de la recalculation.

---

# 32. DRAW SOURCE RECONCILIATION

Créer :

```text
draw_source_observations
```

Un même tirage peut être observé par plusieurs sources :

```text
DRAW 123
 ├── source A → X
 ├── source B → X
 ├── source C → X
 └── source officielle → X
```

Ou :

```text
DRAW 123
 ├── source A → X
 ├── source B → Y
 └── source officielle → Y
```

Dans le deuxième cas :

```text
CONFLICT
```

doit être enregistré.

Le système doit conserver :

```text
source
observed_at
payload_hash
observed_result
source_priority
reconciliation_status
```

Ne jamais supprimer une observation simplement parce qu'elle est incorrecte.

Elle fait partie de l'histoire du système.

---

# 33. DRAW PROVENANCE

Chaque tirage canonique doit permettre de remonter :

```text
CANONICAL DRAW
      ↓
DRAW VERSION
      ↓
SOURCE OBSERVATION
      ↓
COLLECTION EVENT
      ↓
RAW OBJECT
      ↓
PAYLOAD HASH
      ↓
COLLECTOR VERSION
      ↓
COLLECTION TIMESTAMP
```

Objectif :

> Toute donnée utilisée par une recherche doit pouvoir être auditée jusqu'à sa source RAW.

---

# 34. DRAW COMPLETENESS

Créer un contrôle de complétude.

Le système doit pouvoir répondre :

```text
Tirages attendus : 1 250
Tirages détectés : 1 247
Tirages validés : 1 245
Tirages frozen : 1 244
Tirages settled : 1 243
```

et identifier exactement :

```text
DRAW #1234 → MISSING
DRAW #1237 → INVALID
DRAW #1240 → SETTLEMENT_PENDING
```

Créer une métrique :

```text
draw_registry_completeness
```

---

# 35. DRAW INTEGRITY CHECK

Créer un job périodique :

```text
verify_draw_registry
```

Il doit rechercher :

* doublons ;
* trous ;
* numéros invalides ;
* dates incohérentes ;
* versions orphelines ;
* RAW manquant ;
* source manquante ;
* prédiction sans tirage ;
* settlement sans tirage ;
* dataset faisant référence à une version inexistante ;
* canonical version inexistante ;
* transitions d'état invalides.

---

# 36. REGISTRE CONSULTABLE

Créer dans le Web Console une page :

```text
DRAW REGISTRY
```

Colonnes :

```text
Draw ID
Date
Heure prévue
Heure réelle
Jeu
Type
Séquence
Résultat
Version canonique
Source
Statut
Validation
Prédictions
Settlement
Anomalies
```

Filtres :

```text
date
game
draw_type
status
source
validation_status
settlement_status
has_prediction
has_conflict
has_correction
```

---

# 37. FICHE DÉTAILLÉE D'UN TIRAGE

En cliquant sur un tirage :

```text
DRAW DETAILS
```

afficher :

### Identité

```text
draw_id
external_draw_id
game
game_version
draw_type
date
sequence
```

### Résultat

```text
winning_numbers
positions
canonical_version
```

### Sources

```text
source A
source B
source officielle
```

### Provenance

```text
RAW object
hash
collector version
timestamps
```

### Prédictions

```text
models
strategies
predictions
scores
```

### Settlement

```text
hits
Turbo 2
Turbo 3
Turbo 4
Turbo 5
ROI
profit/loss
```

### Historique

```text
versions
corrections
events
anomalies
```

---

# 38. API DU DRAW REGISTRY

Créer au minimum :

```text
GET    /draws
GET    /draws/{draw_id}
GET    /draws/{draw_id}/versions
GET    /draws/{draw_id}/sources
GET    /draws/{draw_id}/predictions
GET    /draws/{draw_id}/settlements
GET    /draws/{draw_id}/history
GET    /draws/missing
GET    /draws/conflicts
GET    /draws/scheduled
POST   /draws/{draw_id}/reconcile
POST   /draws/{draw_id}/confirm
```

Les opérations sensibles doivent être authentifiées et auditées.

---

# 39. RÈGLE ABSOLUE

Le **Draw Registry devient le point de référence temporel du système**.

Ne plus utiliser :

```text
latest API result
```

comme vérité.

Ne plus utiliser :

```text
date
```

comme identité d'un tirage.

Ne plus utiliser :

```text
winning_numbers
```

sans version/provenance.

La chaîne officielle devient :

```text
SCHEDULE
   ↓
DRAW REGISTRY
   ↓
SOURCE OBSERVATIONS
   ↓
RAW DATA
   ↓
DRAW VERSION
   ↓
CANONICAL DRAW
   ↓
PREDICTIONS
   ↓
SETTLEMENT
   ↓
RESEARCH
```

Le registre des tirages doit donc être considéré comme une **infrastructure fondamentale du projet**, au même niveau que la base de données, le stockage RAW et le moteur de recherche.

---

# 40. CRITÈRE D'ACCEPTATION DU DRAW REGISTRY

Le système est accepté uniquement si, pour un tirage donné, nous pouvons partir de :

```text
DRAW ID
```

et retrouver sans ambiguïté :

```text
1. son identité ;
2. son jeu ;
3. sa version du jeu ;
4. sa date ;
5. son heure prévue ;
6. son heure réelle ;
7. son numéro de séquence ;
8. toutes ses observations sources ;
9. son RAW original ;
10. toutes ses versions ;
11. sa version canonique ;
12. ses numéros dans leur ordre ;
13. ses validations ;
14. ses anomalies ;
15. toutes les prédictions qui le ciblaient ;
16. les modèles utilisés ;
17. les stratégies utilisées ;
18. les résultats de settlement ;
19. les résultats Turbo ;
20. les métriques économiques ;
21. les findings scientifiques ;
22. l'historique complet des modifications/corrections.
```

Aucune de ces informations ne doit dépendre d'une donnée volatile provenant directement de l'API externe.

Le Draw Registry est notre **mémoire officielle des tirages**.
