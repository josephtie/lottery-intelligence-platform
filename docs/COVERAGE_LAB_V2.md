# Coverage Laboratory v2 (M10)

Module : `src/lottery_intelligence_platform/lab_coverage.py`
Endpoint : `GET /api/lab/coverage`
Console : Laboratoire → onglet « Simulation & Couverture », panneau Coverage Laboratory.

Mesure quantitative de l'effet de la construction d'un portefeuille de grilles.
Ce n'est pas un prédicteur : aucun résultat de tirage n'est lu — le portefeuille
est construit à partir de la combinatoire seule.

## Algorithme

**Passe 1 — appariement disjoint.** Le pool 1–90 est mélangé (seed) puis découpé
en k-sous-ensembles mutuellement disjoints. Tant que `k × n_tickets ≤ 90`,
l'overlap de paires est exactement 0 et le nombre de numéros couverts est maximal
par construction.

**Passe 2 — recyclage à rejet.** Quand le pool est épuisé, des candidats sont
tirés uniformément ; on accepte celui qui partage le moins de paires déjà
couvertes (30 essais par ticket, garde `40 × n_tickets`). Pour `pick_size = 1`
la collision se mesure sur les numéros couverts.

**Baseline RANDOM.** `baselines` portefeuilles uniformes indépendants, même
budget/nombre de tickets/taille de grille, seed dérivé (`seed + 1`). Mêmes
métriques calculées, moyenne et p90 rapportés.

## Règle de gain et économie

La règle vient de `catalog.payout_rule_versions` (`turbo_fixed_odds`) — jamais
de cote codée en dur. La version est sélectionnable via `rule_version` ; par
défaut la plus récente `VERIFIED_OFFICIAL` est utilisée.

Convention identique à `settlement.py` : un ticket de `pick_size` numéros gagne
si tous ses numéros figurent parmi les `positions` premières boules tirées de la
variante (Turbo k → `positions = k`). La zone gagnante W est un sous-ensemble
uniforme de taille `positions` parmi 90.

- `p_win_per_ticket = C(positions, k) / C(90, k)`
- `gross_payout = stake × multiplier` ; `net = gross − stake`
- `EV_ticket = p_win × stake × multiplier − stake`
- `EV_portfolio = n × EV_ticket` — **linéaire, indépendante de la couverture**
- `RTP = p_win × multiplier` (≈ 0,60 pour toutes les variantes Turbo)

## P(au moins une grille gagnante)

`probability_at_least_one_win` — la métrique principale :

**EXACT** dans deux cas :

1. `pick_size ≥ positions` : le gain exige que le ticket égale la zone W →
   `P = n_tickets_distincts / C(90, positions)` (immédiat).
2. Union couverte `u` suffisamment petite
   (`Σ_m C(u,m) ≤ 200 000`) : décomposition hypergéométrique
   `P = Σ_m C(u,m)·C(90−u,v−m)/C(90,v) × frac(m-sous-ensembles de U contenant
   un ticket)`, où la fraction est énumérée exactement.

**MONTE_CARLO** sinon : `mc_sims` tirages de W (seed explicite), intervalle de
Wilson 95 % rapporté, méthode explicitement étiquetée approximation —
jamais présentée comme exacte.

## Métriques retournées

Budget, tickets, mise unitaire, reste non alloué, `pick_size`, variante, zone
gagnante, règle (version + statut de vérification + multiplicateur) ;
par portefeuille : numéros couverts, paires couvertes, overlap moyen,
écart-type des apparitions, `probability_at_least_one_win` (+ méthode,
IC Monte-Carlo), EV par ticket / portefeuille, RTP, perte attendue ;
comparaison OPTIMISÉ vs RANDOM.

## Limites

- La couverture modifie la **forme** du risque (P(≥1 gain), variance, nombre de
  petits gains possibles), **jamais l'espérance** : l'EV reste `n × EV_ticket`.
- Un portefeuille optimisé peut afficher une P(≥1) légèrement inférieure à la
  moyenne aléatoire sur certains paramètres : disjoint ≠ supérieur en probabilité
  de gain ; seule la diversité combinatoire est garantie.
- `pick_size ≠ 2` : extension hypothétique de la règle positionnelle (les règles
  officielles Turbo exigent 2 numéros) — documenté comme tel, aucune cote réelle
  n'est revendiquée.
- Pas de lecture de tirages, pas de fuite temporelle possible.

## Validation

`tests/unit/test_lab_coverage.py` (22 tests) : appariement disjoint, recyclage,
`tickets=1`, `pick_size∈{1,5}`, budget non multiple, calcul exact sur petit
univers contrôlé (brute-force C(10,3)), Monte-Carlo reproductible et cohérent
avec l'exact, linéarité de l'EV, règle issue du catalogue (multiplicateur
injecté, aucune constante), reproductibilité par seed, comparaison random.

`tests/integration/test_lab_coverage.py` (4 tests, `LOTTERY_TEST_DATABASE_URL`) :
résolution de la règle depuis `catalog.payout_rule_versions`, version explicite,
rejet de version inconnue, bout-en-bout.
