Tu es maintenant responsable du STRATEGY LAB et du PROFITABILITY LAB du LOTTERY INTELLIGENCE PLATFORM.

Le but n'est pas de promettre des gains.

Le but est de déterminer expérimentalement si certaines stratégies ont historiquement et prospectivement produit des résultats économiquement intéressants.

==================================================
TURBO
=====

Implémenter les stratégies Turbo comme des objets configurables et versionnés.

Configuration initiale :

Turbo 2 = cote 2400
Turbo 3 = cote 800
Turbo 4 = cote 400
Turbo 5 = cote 240

NE PAS coder ces valeurs en dur.

Créer :

strategy
strategy_version
payout_rule_version

==================================================
STRATEGY ENGINE
===============

Une stratégie doit définir :

* modèle ;
* features ;
* sélection ;
* top K ;
* règles ;
* mise ;
* payout rule ;
* bankroll policy.

Une stratégie doit être reproductible.

==================================================
SIMULATION
==========

Créer un moteur :

simulate_strategy()

Entrées :

dataset snapshot
model version
strategy version
payout rules
stake policy
bankroll initiale

Sorties :

tickets
hits
payout
stake
net profit
ROI
bankroll curve
drawdown
losing streak
profit factor.

==================================================
PROFITABILITY
=============

Calculer au minimum :

gross_payout
total_stake
net_profit
ROI
maximum_drawdown
profit_factor
longest_losing_streak
break_even_rate
risk_of_ruin lorsque mathématiquement pertinent.

==================================================
IMPORTANT
=========

Ne jamais sélectionner une stratégie uniquement sur :

* hit rate ;
* fréquence ;
* nombre de bons résultats récents.

Une stratégie doit être évaluée sur :

* OOS ;
* walk-forward ;
* stabilité ;
* plusieurs périodes ;
* coût réel ;
* règles de paiement ;
* drawdown ;
* séries de pertes.

==================================================
PROSPECTIVE
===========

Créer un moteur qui enregistre les prédictions AVANT le tirage.

Chaque prediction_run doit contenir :

target_draw
generated_at
dataset_snapshot
model_version
strategy_version
parameters
candidates
scores.

Une fois le tirage connu :

prediction_outcome

est automatiquement généré.

Il doit être impossible de modifier rétroactivement une prédiction sans laisser une trace d'audit.

==================================================
NO EDGE
=======

Prévoir explicitement :

NO_EDGE
WATCH
INSUFFICIENT_DATA
EXPERIMENT_ONLY
PROMISING

La plateforme doit pouvoir conclure :

"aucun avantage démontré"

sans produire artificiellement une stratégie.

==================================================
PORTFOLIO
=========

Prévoir à terme la possibilité de comparer plusieurs stratégies dans un portefeuille simulé.

Exemple :

Turbo 2
Turbo 3
Turbo 4
Turbo 5

avec différentes allocations de bankroll.

Ne pas optimiser agressivement les allocations avant validation OOS.

==================================================
LIVRABLES

Créer :

strategy engine
Turbo laboratory
backtest strategy engine
profitability engine
bankroll simulator
prospective prediction engine
outcome evaluator
portfolio simulator

Créer :

docs/PROFITABILITY_PROTOCOL.md

Le document doit préciser clairement la différence entre :

statistical performance
economic performance
historical simulation
OOS performance
prospective performance
actual realized performance.
