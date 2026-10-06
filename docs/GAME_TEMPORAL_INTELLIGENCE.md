# Game Temporal Intelligence — couche d'observation temporelle

**Statut : couche d'observation en lecture seule. Ce n'est PAS un modèle
prédictif, PAS un sélecteur de numéros, PAS une modification du protocole
prospectif.**

## Objectif

Pour chaque jeu (draw_type), construire un profil historique JEU × MODÈLE
permettant de répondre à des questions d'observation :

- Quels modèles ont été régulièrement performants sur CE jeu ?
- Cette performance est-elle stable dans le temps ?
- Existe-t-il une différence entre les jours de la semaine ?
- Un changement de régime est-il détectable ?
- La performance observée reste-t-elle supérieure au nul quand
  l'échantillon grandit ?

Ces réponses sont des **observations statistiques**. Aucune n'est
transformée en règle de sélection ni en avantage prédictif.

## Modèle de données

Aucune migration. La couche réutilise exclusivement :

- `core.draws` + `core.draw_versions` (VALID) + `core.draw_numbers`
  (WINNING) — historique des tirages par jeu ;
- `research.prediction_outcomes` — outcomes prospectifs scellés
  (matrice inter-jeux) ;
- les 13 modèles de `lab_matrix.MATRIX_MODELS`, rejoués walk-forward
  avec le même mécanisme que `lab_matrix.evaluate_game`.

### Séries source

Pour un jeu et un modèle : la **série de hits walk-forward**
`[{date, hits}]` — à l'index `i`, le modèle ne voit que `hist[:i]`
(`warmup = 20` tirages minimum avant le premier point de série).

## Segmentation stricte par jeu

Chaque `draw_type` a son propre historique. Aucune agrégation ne mélange
deux jeux : `game_profile()` est appelée par draw_type et les résultats
sont retournés par jeu. Le même modèle peut avoir des profils très
différents sur deux jeux — cette information reste séparée.

## Axe temporel

Chaque observation porte :

- `date` — `core.draws.scheduled_date` ;
- `iso_week` — `date.isocalendar()` → `YYYY-Www` ;
- `weekday` — `date.weekday()` (0 = lundi).

Agrégations :

- **hebdomadaire** (`weekly_aggregate`) : n, moyenne de hits, ≥1/≥2/≥3 %
  par semaine ISO ;
- **jour de semaine** (`weekday_aggregate`) : mêmes métriques en
  comparant lundi↔lundis, mardi↔mardis, etc.

Une régularité affichée n'est **pas** une conclusion de structure
prédictive — c'est une observation à confirmer par un échantillon.

## Profil de spécialisation

Pour chaque JEU × MODÈLE (`model_profile`) :

| Champ | Définition |
|---|---|
| `n` | tirages rejoués |
| `mean_hits` | moyenne des hits par tirage |
| `median_hits` | médiane |
| `ge1/ge2/ge3_pct` | % de tirages avec ≥1 / ≥2 / ≥3 hits |
| `best_ge1_streak` | plus longue série de tirages ≥1 hit |
| `worst_zero_streak` | plus longue série de tirages à 0 hit |
| `consistency` | indice de constance (voir ci-dessous) |
| `trend` | moyenne des 4 dernières semaines vs le reste |
| `vs_null` | comparaison à l'attendu hypergéométrique exact |
| `change_point` | observation de rupture (si détectée) |
| `paired_vs_null` | différence appariée vs null_model_benchmark |

## Consistency Score

**Objectif : distinguer "élevé et stable" de "élevé mais volatile".**
Ce n'est ni une probabilité, ni une chance de gain, ni une probabilité
de succès — c'est une mesure de constance.

Formule : pour les moyennes hebdomadaires `m_i` de la série de hits :

```
CV      = sd(m_i) / mean(m_i)              (coefficient de variation)
index   = max(0, 1 - CV)        ∈ [0, 1]
```

- `index = 1` → même niveau moyen chaque semaine (parfaitement stable) ;
- `index → 0` → niveau hebdomadaire chaotique.

Classes documentées : `CV < 0.35` → `stable` ; `0.35 ≤ CV < 0.60` →
`mixed` ; `CV ≥ 0.60` → `volatile`. Non calculable si < 2 semaines
observées ou moyenne nulle. Le niveau (`mean_hits`) est toujours
affiché séparément — un modèle faible et stable n'est pas "meilleur".

## Référence nulle

Deux niveaux, jamais confondus :

1. **Attendu hypergéométrique exact** — pour `pick = k`, tirage de 5
   numéros dans 90 : `hits ~ Hypergeom(90, k, 5)`,
   `E[hits] = 5k/90`, `P(≥t)` exact par somme de combinaisons.
   `vs_null` compare les taux observés à cet attendu et ajoute un test
   binomial bilatéral sur l'indicateur ≥1.
2. **Comparaison appariée** (`paired_vs_null`) — le modèle et
   `null_model_benchmark` rejouent **les mêmes tirages** ; la
   différence moyenne de hits est testée par permutation sign-flip
   (199 simulations seedées). Mesure "mieux que le nul sur tirages
   identiques" — pas un avantage prédictif démontré.

Hiérarchie stricte : performance brute ≠ supérieur au hasard ≠
avantage prédictif ≠ rentabilité.

## Analyse des régimes

`change_point_observation` réutilise `drift.detect_change_point` :
vecteurs hebdomadaires de comptage des hits `[c0 … c5]` → meilleure
coupure χ² + p empirique par permutation (199, seedée). Émis seulement
si `p ≤ 0.05` et ≥ 6 semaines. Le résultat est une **observation
descriptive** ("changement détecté autour de YYYY-Www") — jamais une
règle de sélection.

## Seuils d'échantillon (documentés)

| n | Niveau | Comportement |
|---|---|---|
| < 10 | `insufficient` | statistiques masquées, "Échantillon insuffisant" |
| 10–39 | `preliminary` | statistiques affichées + badge "Observation préliminaire" |
| ≥ 40 | `adequate` | cohérent avec `MIN_WF` de la matrice |

Une conclusion forte n'est jamais affichée avec un petit échantillon.

## Anti-leakage

- `as_of` : `dated_history` filtre `scheduled_date <= as_of` ;
- walk-forward : le modèle à l'index `i` ne voit que `hist[:i]` —
  strictement antérieur (même construction que `lab_matrix`) ;
- la matrice inter-jeux ne lit que des outcomes prospectifs déjà
  scellés et soldés, eux aussi bornés à `as_of` ;
- seeds déterministes : `_stable_seed` (SHA-256) — les agrégations
  sont reproductibles, indépendantes de `PYTHONHASHSEED`.

## API

- `GET /api/lab/game-profiles?draw_type=<code|name>&as_of=YYYY-MM-DD`
  — profil temporel complet d'UN jeu (13 modèles, mis en cache).
- `GET /api/lab/game-matrix?as_of=YYYY-MM-DD`
  — matrice JEU × MODÈLE calculée sur les outcomes prospectifs
  scellés uniquement ; cellules étiquetées par niveau d'échantillon.

## Frontend

Onglet « 🧠 Profils des jeux » du Laboratoire :

- sélecteur de jeu (et de modèle) ;
- profil actuel : classement descriptif JEU × MODÈLE ;
- évolution hebdomadaire du modèle sélectionné ;
- comparaison par jour de semaine ;
- alertes analytiques descriptives (rupture, dégradation, amélioration,
  échantillon insuffisant) ;
- matrice inter-jeux prospective.

## Interprétation et limites

- Un `mean_hits` au-dessus de l'attendu avec `binomial_p_ge1` élevé
  n'est PAS un signal — c'est du bruit compatible avec le hasard.
- `paired_vs_null.permutation_p` significatif sur ~200 tirages reste à
  confronter à la multiplicité (13 modèles × N jeux) — la correction
  FDR existe dans la matrice de performance, pas ici : cette couche
  observe, elle ne juge pas.
- Une "rupture" peut venir d'un changement de règle, d'un trou de
  collecte ou de bruit — le libellé le rappelle.
- Le Consistency Score mesure la régularité du niveau, pas sa valeur.

## Observation / hypothèse / preuve

- **Observation** : tout ce que cette couche affiche (descriptif,
  échantillon-documenté).
- **Hypothèse** : une régularité devient hypothèse quand elle est
  formulée a priori dans `research.hypotheses` — pas ici.
- **Preuve** : exige prospective scellée, puissance, FDR — le
  protocole prospectif existant, que cette couche ne touche pas.

## Ce que cette couche ne modifie pas (garanti)

`generate_predictions`, les 13 pickers, le null, le scoring, le
settlement, le protocole prospectif, les règles Turbo, les résultats
scellés : aucun. Aucune écriture en base ; aucune nouvelle table.
