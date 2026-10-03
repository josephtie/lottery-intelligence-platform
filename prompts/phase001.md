# PROMPT 11 — ORCHESTRATEUR DES TIRAGES, CRON & SETTLEMENT DES PRÉDICTIONS

## RÔLE

Tu es l’architecte DevOps/Data Engineer/Research Engineer responsable de l’orchestration temporelle du nouveau **Lottery Intelligence Platform**.

Ta mission est de concevoir et implémenter un système robuste permettant de :

1. récupérer automatiquement les nouveaux résultats de tirage ;
2. détecter exactement lorsqu’un nouveau tirage apparaît ;
3. valider le résultat ;
4. le figer dans l’historique scientifique ;
5. retrouver toutes les prédictions qui correspondent à ce tirage ;
6. comparer les prédictions aux résultats réels ;
7. calculer les performances des modèles et stratégies ;
8. calculer les résultats économiques des stratégies Turbo ;
9. alimenter la mémoire de recherche ;
10. produire les métriques OOS et prospectives ;
11. garantir qu’aucune prédiction ne puisse être modifiée après le tirage ;
12. rendre toute la chaîne idempotente, observable et récupérable après panne.

---

# 1. PRINCIPLE FONDAMENTAL

Le système doit respecter strictement :

```text
PREDICTION
     ↓
PREDICTION LOCK
     ↓
DRAW
     ↓
VALIDATION
     ↓
FREEZE
     ↓
SETTLEMENT
     ↓
PERFORMANCE
     ↓
KNOWLEDGE
```

Une prédiction doit exister AVANT la connaissance du résultat.

Il est interdit de recalculer rétroactivement une prédiction avec des données postérieures au tirage.

Il est interdit de modifier silencieusement :

* dataset_version ;
* model_version ;
* strategy_version ;
* features ;
* scores ;
* candidats ;
* paramètres ;
* stake ;
* payout rule ;
* timestamp de génération.

Toute correction doit produire un nouvel événement/version et conserver l'historique.

---

# 2. NE PAS CONSTRUIRE UN SIMPLE SYSTÈME DE CRON

Utilise les cron comme mécanisme de déclenchement/détection.

Ne construis pas une chaîne fragile du type :

```text
cron 10:00
   ↓
cron 10:05
   ↓
cron 10:10
   ↓
cron 10:15
```

car un retard du fournisseur ou une panne peut casser toute la chaîne.

Construis plutôt :

```text
CRON COLLECTEUR
       ↓
NOUVEAU TIRAGE ?
       ↓
EVENT DRAW_DETECTED
       ↓
VALIDATION
       ↓
FREEZE
       ↓
EVENT DRAW_VALIDATED
       ↓
SETTLEMENT
       ↓
PERFORMANCE
       ↓
KNOWLEDGE
```

Chaque étape doit être idempotente.

---

# 3. COLLECTE DES RÉSULTATS

Créer un job :

```text
collect_results
```

Fréquence par défaut :

```text
toutes les 5 minutes
```

Exemple :

```cron
*/5 * * * *
```

Le collecteur doit :

1. interroger la source officielle/configurée ;
2. récupérer le dernier résultat disponible ;
3. conserver la réponse RAW originale ;
4. calculer son hash ;
5. enregistrer :

   * source ;
   * collector_version ;
   * collected_at ;
   * payload_hash ;
   * HTTP/status ;
   * draw identifier ;
6. déterminer si le tirage est nouveau.

Si aucun nouveau tirage :

```text
NO_NEW_DRAW
```

Si nouveau tirage :

```text
NEW_DRAW_DETECTED
```

Ne jamais créer deux tirages logiques identiques simplement parce que le collecteur a exécuté deux fois.

Les événements de collecte, eux, doivent être conservés.

---

# 4. VALIDATION DU RÉSULTAT

Créer :

```text
validate_draw
```

La validation doit vérifier au minimum :

### Structure

* format de réponse ;
* date ;
* heure ;
* identifiant du tirage ;
* type de tirage ;
* nombre de numéros.

### Valeurs

* plage autorisée ;
* absence de valeurs invalides ;
* absence de doublons lorsque les règles du jeu l'interdisent.

### Cohérence

* tirage déjà connu ;
* tirage manquant ;
* tirage en doublon ;
* ordre des numéros ;
* modification d'une donnée déjà connue.

### Source

Comparer avec les sources secondaires lorsqu'elles existent.

En cas de conflit :

```text
DATA_CONFLICT
```

Ne jamais choisir silencieusement une source.

---

# 5. FREEZE DU TIRAGE

Après validation, créer une opération :

```text
freeze_draw
```

Le tirage devient une référence historique immuable.

Créer/enregistrer :

```text
draw_id
draw_version
dataset_version
raw_object_id
validated_at
frozen_at
validation_status
source_hash
```

Si une source corrige ultérieurement le résultat :

NE PAS écraser l'ancien en silence.

Créer :

```text
draw_correction
```

avec :

```text
old_version
new_version
reason
source
detected_at
approved_at
```

---

# 6. PREDICTION CUTOFF GUARD

Créer un mécanisme :

```text
prediction_cutoff_guard
```

Chaque prédiction doit contenir au minimum :

```text
prediction_id
target_draw_id
generated_at
dataset_version
model_version
strategy_version
feature_set_version
parameters
candidates
scores
stake
status
```

Avant le tirage :

```text
PENDING
```

À l'heure limite :

```text
LOCKED
```

Après verrouillage :

```text
IMMUTABLE
```

Une prédiction LOCKED ne peut plus être modifiée.

Toute tentative doit être rejetée et auditée.

---

# 7. SETTLEMENT DES PRÉDICTIONS

Créer :

```text
settle_predictions
```

Après validation/freeze d'un tirage, rechercher :

```sql
WHERE target_draw_id = current_draw_id
AND status IN ('LOCKED', 'PENDING')
```

Pour chaque prédiction :

```text
PREDICTION
     ↓
ACTUAL DRAW
     ↓
COMPARISON
```

Calculer au minimum :

* numéros prédits ;
* numéros réellement tirés ;
* nombre de correspondances ;
* positions correspondantes lorsque pertinent ;
* top-K hit ;
* hit/miss ;
* score prédictif ;
* rang réel ;
* métriques de calibration lorsque disponibles.

Créer un :

```text
prediction_outcome
```

sans modifier la prédiction originale.

---

# 8. TURBO SETTLEMENT

Les règles Turbo doivent être entièrement versionnées.

Configuration initiale :

```text
Turbo 2 → parmi les 2 premiers numéros → cote 2400
Turbo 3 → parmi les 3 premiers numéros → cote 800
Turbo 4 → parmi les 4 premiers numéros → cote 400
Turbo 5 → parmi les 5 numéros gagnants → cote 240
```

NE PAS coder ces valeurs en dur.

Créer une entité/version :

```text
payout_rule
payout_rule_version
```

Le settlement doit produire séparément :

```text
Turbo 2
Turbo 3
Turbo 4
Turbo 5
```

avec :

```text
stake
hit
payout
gross_profit
net_profit
ROI
```

---

# 9. STRATEGY SETTLEMENT

Pour chaque stratégie active au moment de la prédiction :

```text
strategy_id
strategy_version
prediction_id
draw_id
```

calculer :

```text
total_stake
total_payout
net_profit
ROI
maximum_drawdown
profit_factor
longest_losing_streak
hit_rate
```

Ne jamais mélanger :

```text
historical backtest
```

avec :

```text
out-of-sample
```

ni :

```text
prospective
```

ni :

```text
realized
```

Chaque résultat doit avoir un type explicite :

```text
IN_SAMPLE
VALIDATION
WALK_FORWARD
OUT_OF_SAMPLE
PROSPECTIVE
REALIZED
```

---

# 10. PIPELINE APRÈS CHAQUE TIRAGE

Implémenter le workflow :

```text
DRAW DETECTED
      ↓
RAW STORED
      ↓
VALIDATE
      ↓
FREEZE
      ↓
LOCK CHECK
      ↓
SETTLE PREDICTIONS
      ↓
SETTLE TURBO
      ↓
CALCULATE STRATEGY METRICS
      ↓
UPDATE MODEL METRICS
      ↓
UPDATE PROSPECTIVE METRICS
      ↓
CREATE FINDINGS
      ↓
UPDATE KNOWLEDGE GRAPH
      ↓
ALERTS
```

Chaque étape doit être :

* idempotente ;
* transactionnelle lorsque nécessaire ;
* reprise après panne ;
* journalisée ;
* observable.

---

# 11. RETRY ET RECOVERY

Une panne ne doit jamais entraîner une perte de données.

Exemple :

```text
collect OK
validate OK
freeze OK
settlement FAILED
```

Au redémarrage :

```text
settlement
```

doit reprendre automatiquement.

Ne pas refaire inutilement :

```text
collect
validate
freeze
```

Utiliser des statuts explicites :

```text
DETECTED
VALIDATING
VALIDATED
FROZEN
SETTLING
SETTLED
FAILED
RETRY_REQUIRED
```

Prévoir :

```text
retry_count
last_error
last_attempt_at
next_retry_at
```

---

# 12. CRONS RECOMMANDÉS

Implémenter au minimum :

### Collecte

```cron
*/5 * * * * collect_results
```

### Daily summary

```cron
0 23 * * * daily_research_summary
```

### Weekly report

```cron
30 23 * * 0 weekly_research_report
```

### PostgreSQL backup

```cron
0 2 * * * backup_postgresql
```

### RAW/MinIO backup

```cron
30 2 * * * backup_raw_storage
```

### Backup verification

```cron
0 3 * * * verify_backups
```

Les horaires doivent être configurables par timezone.

Timezone initiale :

```text
Africa/Abidjan
```

Ne jamais supposer que l'heure du serveur correspond à celle du jeu.

---

# 13. EVENT-DRIVEN PREFERRED

Si l'architecture le permet, utiliser :

```text
scheduler
    ↓
collector
    ↓
event
    ↓
workers
```

plutôt que de mettre toute la logique dans cron.

Par exemple :

```text
DRAW_DETECTED
DRAW_VALIDATED
DRAW_FROZEN
PREDICTIONS_SETTLED
STRATEGIES_SETTLED
KNOWLEDGE_UPDATED
```

Le système peut utiliser PostgreSQL comme mécanisme de persistance des jobs/events si cela suffit.

Redis/queue ne doit être introduit que si son utilité est démontrée.

---

# 14. OBSERVABILITÉ

Créer des métriques :

```text
collector_success_total
collector_failure_total
new_draw_detected_total
draw_validation_failure_total
draw_conflict_total
prediction_settlement_total
prediction_settlement_failure_total
strategy_settlement_total
job_retry_total
job_duration_seconds
```

Créer un écran :

```text
ORCHESTRATOR HEALTH
```

affichant :

* dernier résultat collecté ;
* dernier tirage validé ;
* dernier tirage frozen ;
* dernières prédictions réglées ;
* jobs en erreur ;
* jobs en attente ;
* retries ;
* dernier backup ;
* état du stockage RAW.

---

# 15. ALERTES

Créer des alertes pour :

### Aucun nouveau résultat

Si aucun nouveau résultat n'est détecté au-delà d'un délai configurable.

### Conflit

```text
DATA_CONFLICT
```

### Résultat invalide

```text
VALIDATION_FAILED
```

### Settlement bloqué

```text
SETTLEMENT_STUCK
```

### Backup défaillant

```text
BACKUP_FAILED
```

### Tentative de modification d'une prédiction verrouillée

```text
IMMUTABLE_PREDICTION_VIOLATION
```

---

# 16. TABLES / ENTITÉS À PRÉVOIR

Ajouter ou confirmer au minimum :

```text
scheduler.jobs
scheduler.job_runs
scheduler.job_events

ingestion.collection_runs
ingestion.raw_objects
ingestion.ingestion_events

core.draws
core.draw_versions
core.draw_corrections

research.predictions
research.prediction_versions
research.prediction_outcomes

research.strategy_settlements
research.model_performance
research.experiment_metrics

research.findings

operations.alerts
operations.audit_events
```

Adapter les noms au modèle PostgreSQL final.

---

# 17. TESTS OBLIGATOIRES

Créer des tests pour :

### Test 1

Même résultat récupéré 10 fois.

Résultat :

```text
1 draw
10 collection events
```

### Test 2

Le collecteur tombe après récupération du RAW.

Le système reprend sans perte.

### Test 3

Validation échoue.

Aucun settlement ne doit avoir lieu.

### Test 4

Deux workers tentent simultanément de régler la même prédiction.

Résultat :

```text
1 settlement
```

et non deux.

### Test 5

Une prédiction LOCKED est modifiée.

Résultat :

```text
REJECTED
AUDITED
```

### Test 6

Settlement échoue après calcul partiel.

Le retry doit produire exactement le même résultat final.

### Test 7

Une source corrige un tirage.

L'ancien résultat doit rester traçable.

### Test 8

Le serveur redémarre au milieu du pipeline.

Le workflow doit reprendre automatiquement.

### Test 9

Une prédiction n'existe pas pour un tirage.

Le tirage doit quand même être enregistré.

### Test 10

Un tirage existe mais aucune stratégie n'est active.

Le résultat doit être conservé sans erreur.

---

# 18. INTERDICTION DU LOOK-AHEAD BIAS

Construire une vérification automatique :

```text
prediction.generated_at
<
draw.frozen_at
```

et vérifier que :

```text
dataset_version
```

utilisé par la prédiction ne contient aucun tirage postérieur à la date limite.

Si violation :

```text
LEAKAGE_DETECTED
```

La prédiction doit être exclue des métriques OOS/prospectives et l'incident doit être enregistré.

---

# 19. RECHERCHE ET MÉMOIRE

Après chaque settlement, alimenter le moteur de connaissance.

Exemple :

```text
Prediction P123
       ↓
Draw D456
       ↓
Outcome O789
       ↓
Strategy S12
       ↓
Metrics
       ↓
Finding F321
```

Le système doit pouvoir répondre ultérieurement :

> Quelles prédictions ont été faites pour ce tirage ?

> Quel modèle les a générées ?

> Quelle version des données a été utilisée ?

> Quelle stratégie était utilisée ?

> Combien de numéros ont été trouvés ?

> Quel a été le résultat Turbo ?

> Quel était le ROI ?

> Cette stratégie avait-elle déjà été testée ?

> Avait-elle déjà échoué auparavant ?

---

# 20. LIVRABLES

Produire :

```text
docs/ORCHESTRATION.md
docs/CRON_SCHEDULE.md
docs/PREDICTION_SETTLEMENT.md
docs/RECOVERY.md
docs/ANTI_LOOKAHEAD.md
```

et :

```text
scheduler/
collector/
settlement/
workers/
monitoring/
```

avec :

* migrations PostgreSQL ;
* jobs ;
* workers ;
* tests ;
* health checks ;
* logs structurés ;
* métriques ;
* documentation.

---

# 21. CRITÈRE DE RÉUSSITE

Le système est considéré comme correctement implémenté uniquement si nous pouvons démontrer :

```text
1. Une prédiction est créée AVANT le tirage.

2. Elle est verrouillée.

3. Le résultat est collecté.

4. Le résultat RAW est conservé.

5. Le résultat est validé.

6. Le résultat est frozen.

7. La prédiction est automatiquement retrouvée.

8. Le résultat réel est comparé à la prédiction.

9. Turbo 2/3/4/5 sont calculés avec la bonne version des règles.

10. Les métriques économiques sont calculées.

11. Le résultat est enregistré dans la mémoire de recherche.

12. Le processus est reproductible.

13. Une panne au milieu du processus est récupérable.

14. Aucun double settlement n'est possible.

15. Aucune donnée postérieure ne peut entrer dans une prédiction historique.

16. Les backups peuvent réellement restaurer le système.
```

---

# RÈGLE FINALE

Ne cherche pas simplement à « faire fonctionner les cron ».

Construis un **système de preuve temporelle** permettant de démontrer, pour chaque prédiction :

```text
QUAND ?
AVEC QUELLES DONNÉES ?
AVEC QUEL MODÈLE ?
AVEC QUELLE STRATÉGIE ?
AVEC QUELS PARAMÈTRES ?
AVANT QUEL TIRAGE ?
QUEL RÉSULTAT RÉEL ?
QUEL ÉCART ?
QUEL GAIN/PERTE ?
QUELLE PERFORMANCE ?
QUELLE CONCLUSION ?
```

L'objectif n'est pas de fabriquer artificiellement des résultats rentables.

L'objectif est de construire une infrastructure capable de déterminer honnêtement, dans le temps, **ce qui fonctionne, ce qui ne fonctionne pas, dans quelles conditions, et avec quel niveau de preuve**.
