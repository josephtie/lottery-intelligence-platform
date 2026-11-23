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

Joseph, avec tes 15 000 résultats, je propose un catalogue de modèles précis, chacun avec une mission, les données utilisées, les tests à exécuter et une règle permettant de décider s'il mérite d'être conservé. L'objectif n'est pas d'accumuler des algorithmes, mais de construire un laboratoire capable de distinguer les observations intéressantes des méthodes qui améliorent réellement les prédictions.

# 1. Les modèles à construire

Je répartirais le laboratoire en six familles.

## Famille A — Comprendre les tirages

![3.8. Histograms — Introduction to College Engineering](https://images.openai.com/static-rsc-4/5RPfyL8AaslvMV_IznuvtQnrKWfX5-bKwLB8o_rnsskK6ZBLWQ4CCZN8xWyf3rF4YIs85pGFgR04gVIPCFtAZWMn-4-ebEifvlvDjCCZh8BPJwrnN8H1IXvi0Gz-HhdRkunDxcd4YF5mrWIqZrZNg7jBsm_IJOqYPaeLZtN5N9Q?purpose=inline)

M01 — Frequency Analyzer

Descriptif

* Données : numéros gagnants, par jeu, position et période.

* Travail : calculer les fréquences observées et les comparer aux fréquences théoriques.

* Résultat : tableaux de fréquences, intervalles d'incertitude et écarts observés.

* Limite : un numéro fréquent dans le passé n'est pas automatiquement plus probable au prochain tirage.

![Major explosions and paroxysms at Stromboli (Italy): a new historical catalog and temporal models of occurrence with uncertainty quantification | Scientific Reports](https://images.openai.com/static-rsc-4/otu7a1zqNf7v8OlNUQddSgUmjbZTARUbT7a4-yzYvikvuzJiWKUmHLJIP_o7sCW1VMl4ZnXqfT22nSBhr1HhLT3ORfcq88ZUFdSxjLQUYuNehP7iilv2k2OPFNNOzw8imKhKVxkI1p3zYHhoqW8tES4c7-d05_L4PbpkuhiOYl4?purpose=inline)

M02 — Delay & Recency Analyzer

Descriptif

* Données : historique chronologique de chaque numéro.

* Travail : mesurer le nombre de tirages depuis la dernière apparition et la distribution des intervalles.

* Résultat : retards actuels, intervalles habituels et écarts atypiques.

* Limite : un retard ne crée pas à lui seul une probabilité accrue de sortie.

![Application of Machine Learning in Constitutive Relationship Prediction of Porous Titanium Materials for Artificial Bone](https://images.openai.com/static-rsc-4/mUMonqXUKS8PKDU8ZLavCsoczGCYWn7dcD08FHSd80Qm0HRKPB-YNhJCyN5Hmv_4MnDEUM7MQ9j-4DEt8mfCk3TpovkFEiAkduKTRw2wJGQlkR8VtbxAf8LfK-C9wFTb5RLxc6dpZzElWucHTQBVfC02kGM5B3liMDPAA9iI2LY?purpose=inline)

M03 — Pair & Co-occurrence Analyzer

Exploratoire

* Données : numéros présents dans un même tirage.

* Travail : comparer les fréquences des paires ou groupes aux attentes du hasard.

* Résultat : associations candidates, tailles d'effet, incertitude et correction des tests multiples.

* Limite : beaucoup de paires testées peuvent produire des coïncidences trompeuses.

## Famille B — Tester si les tirages ont une structure

![13 Permutation Testing | PSY317L Guidebook](https://images.openai.com/static-rsc-4/LntDxwYMR-QbJ5NxbHLNPBbZwIqQjCuyeF95QtIIgTVIJdcDQz66IO4NHnTa7TytJhKDymr4LZtmiVTba_zgJZ6ibSQeBebdmctce10ZwF6HeKTAJET0tmTQtgpBTjxYI6BJoz0EVSbt0gQjHEBIv68HWbyP_2SktK_KJ1Xm-rs?purpose=inline)

M04 — Theoretical & Permutation Null

* Données : règles du jeu et historique validé.

* Travail : générer des résultats de référence conformes aux règles, puis comparer les statistiques observées aux simulations.

* Résultat : mesure de la compatibilité avec le hasard attendu.

* Priorité : très élevée. C'est le garde-fou de nombreux autres modèles.

![Funcionalidades do assistente MQL5 que você precisa conhecer (Parte 05): cadeias de Markov - Artigos MQL5](https://images.openai.com/static-rsc-4/juMCclnaKEpWXq_Q8vQg3mdQWOJ-GjEtyN76SxwQRAI7L4ZApcLe-uv260Mmpi_pqkrrTDLL1RysXOTJx1ypWE-N69P6vTfp9q2-8s9S4iJDniuHiefmiwjJlFiObjZ_LUx_I6flRCBEC7fmODeUEhYGxJlTrvKij73mw7LZN4E?purpose=inline)

M05 — Serial Dependence & Markov

* Données : séquences chronologiques de résultats, transformées en variables adaptées.

* Travail : tester si le tirage précédent apporte une information sur le suivant.

* Résultat : dépendances éventuelles, avec comparaison à une référence indépendante.

* Condition : ne retenir une relation que si elle résiste aux tests hors échantillon.

![Changepoint Detection: PELT, BinSeg, CUSUM | MetricGate](https://images.openai.com/static-rsc-4/ECXlS5aTrdi2Q9yldHylwBKoqu7hjdscIykpeou_Cv7mQYtl0gUr1BYPY6WryTIsGZrVqV_nQdCEnVTchYyf4v0MdxnHEZU_pJm8G8HJl12B7cncr0S3_kOUNhsslb7BAp_heHaIGFmGV9Li-q6DrbxqtPlHBUpDyqAz-uzN7Sk?purpose=inline)

M06 — Change-Point Detector

* Données : fréquences, distributions et caractéristiques successives.

* Travail : détecter d'éventuelles ruptures de distribution.

* Résultat : périodes candidates à examiner, avec estimation de l'incertitude.

* Limite : une rupture apparente peut provenir du bruit, d'un changement de règles ou d'un défaut de collecte.

## Famille C — Estimer des probabilités et produire des candidats

![Exploring Prior, Likelihood, and Posterior Distributions | Krishnadas Mohandas](https://images.openai.com/static-rsc-4/ThNWPMeHXPQSs-uz5GzI7BEZjguqjUlk02bHuukKpoeMHULewJANkmZnZFExyabF3aPIbtQomtKtfCzBHyGStbDrHos0KtyHLf1j33ixp1kNb5r1xxY2wJlZHdVEZzHyFd2HZeE8hfeS2emUlRNL3o7zVZ0ocJMDZDUGWajZovE?purpose=inline)

M07 — Bayesian Probability Model

* Données : observations historiques et hypothèses probabilistes documentées.

* Travail : estimer les probabilités avec leur incertitude et éviter les estimations extrêmes sur de petits échantillons.

* Résultat : distributions de probabilité, intervalles crédibles et prédictions probabilistes.

* Condition : les estimations doivent être évaluées sur des tirages futurs non utilisés pour le réglage.

![What is Monte Carlo Method? Monte Carlo Method Example](https://images.openai.com/static-rsc-4/mtXajeNV4yNZrdA7IIDJK8XUs6xQ9CzL-SFwKHWCInnSpX2slz0CA0LywWBRgns_pzlwjfVq8jePgzEr5_kd-Q1k00heKJ9EkbyZ2ec3qnJhokDLpc02gKZ67RIE0sd7jC_9MT92JM8xCW_E2ei4eLC4SUU4_AEy2-BlAYOHhAo?purpose=inline)

M08 — Monte-Carlo Simulator

* Données : règles officielles, distributions de référence et stratégies candidates.

* Travail : simuler de nombreux scénarios pour estimer les résultats possibles.

* Résultat : distributions de gains, de pertes et d'indicateurs de risque.

* Limite : simuler un grand nombre de tirages ne rend pas les numéros simulés plus prédictifs.

![Frontiers | An interpretable stacking ensemble model for high-entropy alloy mechanical property prediction](https://images.openai.com/static-rsc-4/HwRjKcEpUL4HkqxeT5awG-Ng2eowWhIcos01zC5Qbn7185glA2GweupreEiEWZAOOcEiOUFcouQ7npER4xWJljM5NyKb_fU24_puHr38w8BEU9g73wjXM6RdbOID2C6CF3Sj3vmMOiyRFAIK0cvOmTdRd718yI4z8Hs2rmXhmps?purpose=inline)

M09 — Ensemble & Model Comparison

* Données : sorties des modèles M01 à M07, produites sans fuite temporelle.

* Travail : comparer les modèles seuls à des combinaisons prédéfinies de modèles.

* Résultat : comparaison de scores probabilistes et de performances hors échantillon.

* Condition : un ensemble n'est conservé que s'il apporte une amélioration reproductible par rapport aux références.

## Famille D — Optimiser les sélections et les stratégies

![使用GNN求解组合优化问题\_图神经网络组合优化-CSDN博客](https://images.openai.com/static-rsc-4/7gL-GiZLPDdf_m2ynd76yGLExCH6RkxP6xYhajrEV9qUgR_x4nDnW0Fyw1haLa6g1kTpoHQ8YfEZn1j-8VT3NlWswpqDxhfp57e1UfFc96atCua3as46DI4-VVthWZB2YvK0FJvY5jLHgY4Qaf4XhKQngw9Q4bcEx2RVg8xsBkg?purpose=inline)

M10 — Coverage Optimizer

* Données : combinaisons autorisées, contraintes de sélection et budget défini.

* Travail : répartir les sélections pour améliorer une mesure de couverture choisie.

* Résultat : portefeuilles de combinaisons et comparaison avec une sélection de référence.

* Limite : améliorer la couverture des combinaisons n'augmente pas nécessairement la probabilité de gagner.

![Diversified ETF Portfolio: From Backtesting to Live Trading](https://images.openai.com/static-rsc-4/Ac20eWoH69eZug8my_Y0F9Sga3x7iP0rCW_LxW-O1wRS7_gcgRoCCVUknsGzkuB89uyICNnqJ9RQLA15ORAygDdIC5ow0h6d5XEk1undXiNUqF2tqwv9Fc1eskcwhzqa3JdYRoym0sP9KIYbfJwqiEydnqbcMpEDwaFqxZUGSLw?purpose=inline)

M11 — Turbo Laboratory

* Données : prédictions verrouillées, résultats officiels, mises et versions des règles de paiement.

* Travail : évaluer séparément Turbo 2, Turbo 3, Turbo 4 et Turbo 5.

* Résultat : taux de réussite selon la définition officielle, mises, gains simulés, pertes cumulées, ROI et séries perdantes.

* Condition : distinguer les performances historiques, hors échantillon et prospectives.

![Configuring W\&B Projects with Hydra](https://images.openai.com/static-rsc-4/JuGpoSt6PhIWL45MAsGnuJWSAeg4oF4DYtfvzlO6fONuiHyEQ4rgBljqM7GyNf49QyOuD6epCm90UwiPub3KDA2nsKsJaKwKbtLddgI4neSFahT68pzuyp1JmL-QI30KkRevnrb01une7vGGi67-XI4ApGr-mNPxqHzv7-irZ3k?purpose=inline)

M12 — Walk-Forward & Prospective Evaluator

* Données : snapshots historiques, versions des modèles, prédictions verrouillées et résultats observés.

* Travail : simuler ce que le modèle aurait su à chaque date, puis suivre ses prédictions futures.

* Résultat : performances chronologiques reproductibles et détection des fuites de données.

* Priorité : très élevée. C'est le contrôle qui empêche de confondre ajustement du passé et capacité prédictive.

## Famille E — Conserver la connaissance et accélérer la recherche

![Building a Personal Research Engine with sigint and Claude Code | zircote](https://images.openai.com/static-rsc-4/aAZ4_rhrbHSc_0FcbyFIgZmtNGHS-MPViJ2pcNWuVCSWLhwqHQmrte0kPAmhXd_Qyc4y9XTuifdN4r-0nFUrQJZTphQsttcrlpuj3bIIcy72w5RhPN89PVq3z9XpZml_DjIahMOGY-1m-kW84BvLNNxjKgTf7qsmqjWZcZH7HMY?purpose=inline)

M13 — Experiment Ledger & Knowledge Engine

* Données : hypothèses, versions de datasets, paramètres, résultats et décisions.

* Travail : mémoriser les expériences réussies, négatives, abandonnées ou non concluantes.

* Résultat : historique consultable des connaissances et des pistes déjà explorées.

* Objectif : empêcher Hermes de refaire sans cesse les mêmes tests ou de réinterpréter un échec comme une découverte.

![Data quality dimensions](https://images.openai.com/static-rsc-4/p3H92coHaoH9vmqVEL69tDGfOOA8wrmEYqybL1C7s1vrIsP77OzLeLS17W5yCerbzTYUGvhmm5YlOhPcAdpUSYw5s6bSKXWcAGoih_HRcH-BtHUFqX19yP8CPxhhoDmF0Wbw2huc1QmSkvl1G-t10yA6b1O17dhDzGUXSYpxZDk?purpose=inline)

M14 — Data Quality & Drift Monitor

* Données : registre des tirages, observations des sources, corrections et métriques de distribution.

* Travail : détecter les résultats manquants, conflits, modifications de schéma et changements statistiques.

* Résultat : alertes explicables et blocage des expériences lorsque les données ne sont pas fiables.

## Famille F — Piloter l'ensemble du laboratoire

M15 — Research Orchestrator

Ce n'est pas un modèle prédictif supplémentaire. C'est le chef d'orchestre qui décide quels travaux exécuter, sur quelles données et à quel moment.

Il doit :

* lancer les audits et analyses nécessaires à l'arrivée de nouvelles données ;

* éviter de recalculer des résultats inchangés ;

* déclencher les expériences autorisées selon un budget de calcul ;

* suspendre les pistes sans amélioration mesurable ;

* conserver les preuves et produire un rapport de recherche périodique.

## 2. Dans quel ordre les développer ?

Je ne développerais pas les quinze en parallèle.

Phase 1

Fondations

M01, M02, M04, M12, M14

Qualité, fréquences, retards, références statistiques et validation chronologique.

Phase 2

Recherche

M03, M05, M06, M07

Associations, dépendances, ruptures et probabilités.

Phase 3

Comparaison

M08, M09, M10

Simulations, ensembles et optimisation des sélections.

Phase 4

Stratégies

M11, M13, M15

Turbo, mémoire scientifique et orchestration complète.

Les phases peuvent se chevaucher : le registre des expériences et la mémoire scientifique doivent être prévus dès les fondations, même si leurs fonctions avancées arrivent plus tard.

## 3. Comment le système décidera-t-il de garder un modèle ?

Chaque modèle recevra une fiche de validation comprenant :

| Critère             | Question                                                                               |
| ------------------- | -------------------------------------------------------------------------------------- |
| Qualité des données | Les observations utilisées sont-elles fiables et adaptées au jeu ?                     |
| Référence           | Le modèle fait-il mieux qu'une référence aléatoire correctement définie ?              |
| Robustesse          | Le résultat persiste-t-il sur plusieurs périodes de test ?                             |
| Incertitude         | L'amélioration est-elle suffisamment précise pour être interprétée ?                   |
| Multiplicité        | Le résultat survit-il à la correction des nombreuses hypothèses testées ?              |
| Prospective         | Les prédictions verrouillées confirment-elles les résultats historiques ?              |
| Économie            | Après toutes les mises et tous les paiements, le bilan simulé reste-t-il intéressant ? |

Un modèle pourra être exploratoire, rejeté, à surveiller, soutenu hors échantillon ou soutenu prospectivement. Aucun modèle ne sera qualifié de rentable sur la seule base de son taux de réussite historique.

### Ma recommandation finale

Avec 15 000 résultats, je commencerais par M01 + M04 + M12 + M14, tout en construisant le registre des tirages et le registre des expériences. Ensuite, nous ouvririons progressivement les autres familles.

Ce socle nous permettra de déterminer où les données contiennent une information mesurable, où elles sont simplement compatibles avec le hasard et quelles expériences méritent encore des ressources. Il ne garantit pas qu'un avantage prédictif existe, mais il évite de dépenser l'essentiel du projet à produire des prédictions dont on ne sait pas mesurer la valeur.

