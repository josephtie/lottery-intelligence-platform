Tu es maintenant Lead Research Engineer et ML Engineer du LOTTERY INTELLIGENCE PLATFORM.

Le Data Foundation est considéré comme stable.

Ta mission est de construire le RESEARCH ENGINE.

==================================================
OBJECTIF
========

Créer un laboratoire permettant de tester scientifiquement des hypothèses statistiques sans fuite temporelle et avec traçabilité complète.

Le système doit permettre :

hypothesis
→ experiment
→ dataset snapshot
→ features
→ model
→ backtest
→ walk-forward
→ OOS
→ prospective
→ conclusion
→ knowledge record.

==================================================
RESEARCH LEDGER
===============

Créer :

research.hypotheses
research.experiments
research.experiment_runs
research.experiment_metrics
research.findings

Une expérience doit contenir :

experiment_id
hypothesis
dataset_version
snapshot_id
feature_version
model_version
strategy_version
code_version
configuration
random_seed
created_at
completed_at
status.

==================================================
FEATURE ENGINE
==============

Créer des features versionnées.

Exemples :

* fréquence ;
* retard ;
* fréquence récente ;
* fenêtres glissantes ;
* cooccurrence ;
* séquences ;
* position ;
* saisonnalité éventuelle ;
* transformations statistiques.

IMPORTANT :

Toute feature temporelle doit respecter :

FEATURE(t) = uniquement information disponible avant t.

Créer des tests anti-data-leakage.

==================================================
MODEL REGISTRY
==============

Créer :

models
model_versions
model_runs

Chaque modèle doit avoir :

* nom ;
* version ;
* description ;
* hypothèse ;
* features ;
* paramètres ;
* seed ;
* code version ;
* dataset snapshot.

==================================================
ÉVALUATION
==========

Implémenter séparément :

IN_SAMPLE
VALIDATION
WALK_FORWARD
OUT_OF_SAMPLE
PROSPECTIVE

Ne jamais mélanger les résultats.

==================================================
MÉTRIQUES
=========

Prévoir selon pertinence :

hit rate
precision
recall
lift
ranking metrics
calibration
confidence interval
p-value
multiple testing correction
stability
drawdown
profitability metrics

Ne jamais utiliser une métrique unique pour déclarer un modèle performant.

==================================================
REPRODUCTIBILITÉ
================

Créer :

run_experiment()
reproduce_experiment()
compare_experiments()

La reproduction d'une expérience doit utiliser :

* même snapshot ;
* même version de features ;
* même modèle ;
* même seed ;
* mêmes paramètres.

==================================================
RESEARCH GOVERNANCE
===================

Empêcher :

* future leakage ;
* dataset non versionné ;
* modèle non versionné ;
* expérience non reproductible ;
* conclusion sans OOS lorsque l'OOS est requis ;
* optimisation basée uniquement sur le test final.

==================================================
RÉSULTAT

Une expérience doit pouvoir être classée :

EXPLORATORY
REJECTED
PROMISING
VALIDATED
RETIRED

"PROMISING" n'est pas synonyme de "PROFITABLE".

Une performance statistique n'est pas automatiquement une performance économique.

==================================================
LIVRABLES

Produire :

research engine
model registry
experiment ledger
feature registry
backtesting engine
walk-forward engine
OOS engine
reproduction engine

ainsi que :

docs/RESEARCH_PROTOCOL.md

Ce document devient le protocole officiel du laboratoire.
