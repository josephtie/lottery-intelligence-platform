Tu es maintenant responsable du KNOWLEDGE ENGINE du LOTTERY INTELLIGENCE PLATFORM.

Le système doit apprendre de ses expériences sans réécrire l'historique.

==================================================
OBJECTIF
========

Construire une mémoire scientifique persistante.

Le système doit savoir :

* ce qui a été testé ;
* pourquoi ;
* sur quelles données ;
* avec quelle méthode ;
* avec quel résultat ;
* pourquoi une hypothèse a été acceptée ou rejetée.

==================================================
HYPOTHESIS
==========

Créer :

hypotheses

Chaque hypothèse doit contenir :

hypothesis_id
statement
origin
created_at
status.

==================================================
FINDINGS
========

Créer :

findings

Une finding doit référencer :

hypothesis
experiment
dataset
model
strategy
metrics
conclusion
limitations.

==================================================
REJECTED KNOWLEDGE
==================

Une hypothèse rejetée est une donnée importante.

Exemple :

HYP-00031

"frequency + delay improves Turbo 3"

Testée :

EXP-00124
EXP-00187
EXP-00241

Conclusion :

aucune robustesse OOS suffisante.

Cette information doit empêcher Hermes de recommencer aveuglément la même expérience.

==================================================
SIMILAR EXPERIMENT DETECTION
============================

Créer un mécanisme permettant de rechercher :

* hypothèses similaires ;
* expériences similaires ;
* features similaires ;
* modèles similaires ;
* stratégies similaires.

Avant de lancer une expérience coûteuse, Hermes doit pouvoir demander :

"Cette hypothèse ou une hypothèse proche a-t-elle déjà été testée ?"

==================================================
RESEARCH GRAPH
==============

Prévoir les relations :

Hypothesis
↓
Experiment
↓
Dataset
↓
Feature
↓
Model
↓
Strategy
↓
Prediction
↓
Outcome
↓
Finding

==================================================
KNOWLEDGE QUALITY
=================

Chaque conclusion doit avoir un niveau :

OBSERVATION
HYPOTHESIS
EXPERIMENTAL
OOS_SUPPORTED
PROSPECTIVE_SUPPORTED
REJECTED

Ne jamais appeler "proof" un résultat statistique.

==================================================
HERMES
======

Créer une interface permettant à Hermes de demander :

search_hypotheses()
search_experiments()
search_findings()
find_similar_experiments()
get_model_history()
get_strategy_history()
get_failure_history()

==================================================
OBJECTIF

Après plusieurs années, le système doit avoir une mémoire cumulative des recherches.

La connaissance des échecs doit être aussi importante que celle des succès.
