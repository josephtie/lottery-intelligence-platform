# Audit — `coverage_optimizer.py` (legacy) vs M10 actuel

Source legacy : `lottery-statistics-expert-/models/coverage_optimizer.py`
Équivalent actuel : `src/lottery_intelligence_platform/lab_coverage.py` (M10, exposé via `/api/lab/coverage`)

Statut : **audit documentaire, aucune intégration effectuée.**

## 1. Nature du module

Optimiseur de portefeuille de grilles — **pas un prédicteur**. Le module le dit
explicitement : `E[grille] = P(gain) × mise × cote − mise < 0 pour TOUS les
paris` ; l'optimisation « améliore la couverture, pas l'espérance ».

## 2. Comparaison quantitative

| Dimension | Legacy `coverage_optimizer.py` | M10 actuel `lab_coverage.py` |
|---|---|---|
| Fonction objectif | Maximiser paires distinctes + minimiser overlap (greedy disjoint pairs d'abord) | Maximiser numéros distincts puis paires distinctes (greedy least-covered) |
| Types de paris | Tous : 1N–5N, PN, TURBO_2–5, DC_1N–5N | Générique : `pick_size` numéros parmi 90 (pas de notion de type de pari) |
| Cotes / EV | Oui — table LONACI complète, EV par grille, RTP, EV portefeuille | Non — métriques de couverture uniquement |
| Algorithme | Deux passes : (a) appariement parfait en sous-ensembles disjoints → 0 overlap garanti tant que possible ; (b) recyclage par rejet quand le pool est épuisé | Greedy : numéro le moins couvert + pénalité paires déjà utilisées |
| Complexité | O(n_grids × k × 90) + rejet borné | O(tickets × pick_size × 90) |
| Nombre de tickets | Déduit du budget : `budget // 100 FCFA` | Paramètre explicite `tickets` |
| Mesure de couverture | Paires distinctes, overlaps, % numéros couverts | Numéros distincts, paires distinctes, écart-type des apparitions, overlap |
| **P(≥1 grille gagnante)** | **Oui — calcul exact** par inclusion-exclusion hypergéométrique quand |union| ≤ 25, Monte-Carlo 20 000 sims sinon | **Non — absent** |
| Baseline | 100 portefeuilles aléatoires, seed fixe | 100 portefeuilles aléatoires, seedé |
| Sortie économique | stake, gross, EV total, RTP, verdict explicite | Disclaimer texte (« couverture ≠ probabilité de gain ») |
| Validation croisée événementielle | P(au moins une grille) comparée random vs optimisé | Non |

## 3. Ce que le legacy fait de mieux

1. **P(≥1 grille gagnante)** : c'est la métrique qui compte pour un
   portefeuille — la couverture de paires est un proxy, la probabilité qu'au
   moins une grille soit gagnante est la quantité réelle. Le legacy la calcule
   **exactement** par décomposition hypergéométrique sur l'union des numéros
   (`P(m des 5 gagnants dans l'union) × P(au moins une grille ⊆ m
   sous-ensemble)`) avec bascule Monte-Carlo au-delà de 25 numéros. Le M10
   actuel s'arrête aux paires distinctes — c'est l'écart fonctionnel principal.
2. **Appariement disjoint garanti** : pour les tickets de taille k, la première
   passe produit des sous-ensembles mutuellement disjoints → le maximum de
   paires distinctes est atteint par construction, pas par heuristique.
3. **Économie par pari** : EV et RTP calculés par type de pari, avec le verdict
   honnête « couverture améliorée, EV inchangée » — quantitativement, pas
   seulement en disclaimer.

## 4. Ce que M10 fait de mieux

1. Interface API propre, paramétrable (`tickets`, `pick_size`, `baselines`,
   `seed`), intégrée à la console.
2. Écart-type des apparitions par numéro (mesure d'équilibre du portefeuille).
3. Pas de dépendance SQLite ni de constantes économiques embarquées.

## 5. Distinction méthodologique — obligatoire

Une meilleure couverture de paires **n'augmente ni ne diminue** l'espérance de
gain du portefeuille : l'EV est linéaire dans les grilles. Ce que la couverture
change :

- **P(au moins un gain)** : monte légèrement avec la diversité (effet union),
  plafonné par `n_grids × P(gain)` — la valeur exacte legacy permet de le
  mesurer honnêtement.
- **Variance** : la couverture disjointe *augmente* la probabilité d'au moins
  un petit gain mais n'affecte pas l'espérance (RTP structurel ≈ 0,60).
- Ce n'est jamais un avantage économique : `n × (−40 FCFA/pari)` reste
  `n × (−40 FCFA)`.

## 6. Décision

**`MERGE`** — cible : `lab_coverage.py`.

À porter dans M10 (avec la base PostgreSQL, pas SQLite) :

- la première passe d'appariement disjoint (optimal pour `pick_size` petit) ;
- le calcul exact / Monte-Carlo de `P(≥1 grille gagnante)` sur l'union ;
- les métriques économiques par type de pari **en lisant
  `catalog.payout_rule_versions`**, pas une table de cotes recopiée — la
  version de règle doit être un paramètre d'entrée.

À ne pas porter :

- la table `ODDS` codée en dur (dupliquerait le catalogue versionné) ;
- les dépendances `sqlite3` / `MISE_MIN_PARI` implicites ;
- le mode CLI (le nouveau canal est l'API).

Risque résiduel : faible — le module est un calculateur hors-ligne, sans fuite
temporelle possible (il ne lit pas de tirages). Aucune décision d'intégration
n'est prise ici ; elle attend un accord explicite.
