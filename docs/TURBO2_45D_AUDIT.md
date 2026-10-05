# Audit — Protocole Turbo-2 45 jours (legacy)

Modules audités : `turbo2_engine.py`, `turbo2_selector.py` (logique fusionnée
dans `turbo2_decision.py`), `turbo2_historical_lab.py`, `turbo2_decision.py`,
`turbo2_45d_protocol.json`, `bet_economics.py` (+ `bet_scoring.py`,
`prospective_report.py` en dépendances).

Référence de vérité : la plateforme actuelle — `settlement.py`
(`turbo_settlement`, positions ordonnées), `catalog.payout_rule_versions`
(`official-turbo-position-2026-10`), cohortes prospectives PostgreSQL.

Statut : **audit documentaire, aucune intégration, aucune cohorte créée.**

## 1. Reconstruction du protocole

`turbo2_45d_protocol.json` + code associé définissent l'expérience :

| Élément | Valeur reconstituée |
|---|---|
| `experiment_id` / `protocol_id` | `TURBO2-45D-20261003-v1` (égaux, vérifiés) |
| Statut au moment de l'audit | `DRAFT_NOT_STARTED` — jamais activé |
| Mode | `PAPER_ONLY`, `real_money_enabled=false` |
| Pari | TURBO_2 — mise virtuelle 100 FCFA |
| Horizon | 45 jours : 2026-10-03 → 2026-11-17 (exclus) |
| Jeux | `all_games_eligible_at_activation`, gelés à l'activation, historique ≥ 20 tirages |
| Cadence | une décision par jeu et par tirage cible |
| Sélecteur | `pair_cooccurrence_v1` |
| Modèles d'entrée | les 9 modèles H008 (ordre fixe, égalité stricte vérifiée) : `hot_frequency_v1`, `random`, `cold_delay_v1`, `frequency_delay_v1`, `pair_frequency_v1`, `balanced_v1`, `bayesian_v1`, `monte_carlo_v1`, `ensemble_v1` |

## 2. Mécanique de la décision

1. Chaque modèle produit 5 numéros (validés : exactement 5 distincts, 1–90).
2. Le sélecteur génère les C(5,2)=10 paires par modèle, vote pondéré
   (poids égaux — une carte de poids exige une pré-inscription OOS séparée).
3. La paire de tête = **candidate** si elle est unique ; **NO_BET** en cas
   d'ex æquo ; le `shadow_pair` (paire de tête quoi qu'il arrive) est toujours
   scellé pour permettre le scoring même sans pari.
4. `decision_quality_score` = part de poids des modèles supporters —
   **explicitement pas une probabilité** (`score_interpretation` le dit, plus
   l'avertissement de corrélation entre modèles et le recyclage de modèles
   déterministes par `ensemble_v1`).
5. Gate : `minimum_pair_support` gelé à l'activation ; en dessous → NO_BET
   (`PAIR_SUPPORT_BELOW_FROZEN_GATE`).

## 3. Anti-fuite et intégrité — le point fort du legacy

- **Scellement horodaté** : `turbo2_decisions` enregistre
  `history_max_draw_id` + `sealed_at` ; le scoring vérifie
  `TARGET_ALREADY_OBSERVED_BEFORE_T2_SEAL` — une décision ne peut pas être
  scellée après le tirage cible.
- **Empreintes** : `canonical_hash` SHA-256 (JSON canonique) sur la prédiction
  et sur la provenance (9 champs : experiment_id, version modèle, commit,
  hash des sources modèle/sélecteur/history_loader, paramètres, seed,
  algorithme de seed). Recalculée à chaque cycle ; toute divergence bloque.
- **Protocole gelé** : `activate_protocol` écrit `protocol_sha256` +
  `eligible_games_json` en base ; `_frozen_protocol` exige l'égalité exacte du
  fichier — modifier le protocole après activation = nouvel `experiment_id`
  obligatoire.
- **Activation bloquante** : `validate_protocol_for_activation` exige ~20
  conditions dont : statut ACTIVE, snapshot de la **règle officielle vérifié
  par hash** (fichier JSON épinglé par SHA-256, tous les champs comparés :
  cote, condition de gain, source_url, période d'effet), snapshot de
  **calibration de gate approuvé** (`APPROVED_FOR_PROSPECTIVE`, relecteur,
  manifeste de sources hashé), analyse de puissance gelée, fenêtre de dates
  cohérente avec la période d'effet de la règle.
- **Comparateurs figés au scellement** : paire aléatoire seedée par SHA-256
  (`stable_random_pair` — pas `hash()` de Python, reproductible) et paire
  hot-frequency, toutes deux enregistrées dans la décision pour scoring
  apparié ultérieur.
- **Scoring as-of** : un tirage n'est retenu que si `collected_at ≤ as_of` —
  pas de réécriture du passé.
- **Rapport J+45 immuable** : `archive_j45_report` écrit le fichier en
  `O_EXCL` + `fsync` — jamais écrasé.

## 4. Règle Turbo-2 — compatibilité avec le settlement actuel

| Élément | Legacy | Plateforme actuelle | Verdict |
|---|---|---|---|
| Condition de gain | les 2 numéros dans les **2 premières positions** ordonnées | `predicted_set ⊆ set(ordered_winning[:2])` | ✅ identique |
| Cote | 2400 (`ODDS_LONACI["TURBO_2"]`) | `official-turbo-position-2026-10` ×2400 | ✅ identique |
| Baseline théorique | C(2,2)/C(90,2) = 1/4005 ≈ 0,0002497 | identique | ✅ identique |
| Mise | 100 FCFA virtuel | `DEFAULT_TURBO_STAKE = 100` | ✅ identique |
| Gain brut | `stake × odds` | `stake × multiplier` | ✅ identique |
| Net / ROI | `gross − stake`, `net/stake` | équivalent dans les évaluations | ✅ compatible |

**La sémantique du pari est strictement compatible.** Ce qui ne l'est pas :
SQLite vs PostgreSQL, table `turbo2_decisions` ad-hoc vs cohortes
prospectives versionnées, provenance artisanale vs schéma `research.*`.

## 5. Plan d'analyse — points forts et lacunes

Points forts (rigueur supérieure à la moyenne) :

- binomiale exacte bilatérale vs baseline théorique ; IC de Wilson ;
- **McNemar exact apparié** vs baselines random et hot-frequency (les paires
  comparateurs étant scellées avec la décision, l'appariement est garanti) ;
- FDR Benjamini–Hochberg sur la famille de tests (seuils balayés 1–9 dans le
  lab historique) ;
- analyse de puissance par approximation normale, scénarios break-even
  (P=1/2400) et 2× baseline — avec le rappel honnête que 45 paris ×
  0,0002497 ≈ **1,1 % de chance d'observer ne serait-ce qu'un gain** sous le
  nul (`1 − (1−p0)^45`) et ~12 000 paris nécessaires pour 95 % de chance
  d'en voir un ;
- lab historique : walk-forward strict (`draws[:i]`), split dev/OOS 80/20,
  **aucun seuil auto-sélectionné** — `selected_threshold=None`, décision
  humaine exigée ;
- critères de revue : ≥100 observations scorées par jeu, lift positif, EV net
  positif requis pour toute phase réelle.

Lacunes / réserves :

- **Puissance irrémédiablement faible** : 45 jours × ~6–8 jeux ≈ 300
  paris ; sous le nul on attend ~0,07 gain au total. Même un vrai lift ×2
  serait indétectable de façon fiable. Le protocole le sait (l'analyse de
  puissance l'affiche) mais le nom « 45 jours » suggère une conclusion à
  l'arrivée — c'est en réalité un protocole de **calibration de gate et
  d'accumulation**, pas de démonstration.
- Sélection de seuil : le lab balaie 9 seuils avec FDR — correct en
  diagnostic, mais le gel définitif du `minimum_pair_support` exigeait une
  approbation humaine jamais effectuée (`review_status:
  PENDING_HUMAN_REVIEW`).
- Le protocole n'a jamais été activé : `official_rule_snapshot` et
  `gate_calibration_snapshot` ont des hash `null` — aucune preuve de règle
  n'a été épinglée.
- Corrélation des 9 modèles reconnue mais non traitée (ensemble_v1 réutilise
  les déterministes → le « vote » surévalue le consensus).

## 6. Fuites temporelles — verdict

**Aucune fuite détectée.** Walk-forward strict partout, scellement avant
cible vérifié par `history_max_draw_id`, comparateurs seedés figés au
scellement, scoring avec coupure `as_of`, split OOS jamais utilisé pour
régler le seuil.

## 7. Décisions par fichier

| Fichier | Rôle | Décision |
|---|---|---|
| `turbo2_45d_protocol.json` | protocole (spec) | `NEEDS_RESEARCH` — trame à réutiliser comme gabarit de cohorte pré-enregistrée |
| `turbo2_engine.py` | orchestrateur de l'expérience | `REIMPLEMENT` — mécanique à porter sur le moteur de cohortes ; SQLite et schéma ad-hoc à abandonner |
| `turbo2_decision.py` / `turbo2_selector.py` | sélecteur + gate | `MERGE` — le vote de paires et le gate multi-conditions sont de bons composants ; à recâbler sur les pickers et `catalog.payout_rule_versions` |
| `turbo2_historical_lab.py` | évaluateur walk-forward du gate | `MERGE` — le balayage de seuil dev/OOS + refus d'auto-sélection méritent portage dans l'évaluation des stratégies |
| `bet_economics.py` | évaluateur économique | `MERGE` — voir matrice de migration |
| `turbo2_report.py` (annexe) | reporting | `REJECT_DUPLICATE` — `/api/prospective/*` couvre la fonction |

## 8. Vers `prospective_turbo2_45d_v1` — proposition, non activation

Le protocole legacy est un **bon gabarit** de cohorte pré-enregistrée. S'il
devait être porté, il faudrait définir avant tout début :

- modèles : sous-ensemble des 13 pickers actuels (poids égaux, liste figée) ;
- baseline : `null_model_benchmark` + paire aléatoire SHA-256 seedée ;
- règles : `official-turbo-position-2026-10` (version épinglée, pas de
  table de cotes copiée) ;
- métriques : hit rate vs 1/4005, McNemar vs random, EV net ;
- critères de succès, d'arrêt, de suspension ; seuil de puissance **avant**
  engagement — et honnêteté affichée : 45 jours ≈ 1 % de chance d'un gain
  sous le nul → durée réaliste à recalculer (ou pari à plus haute
  fréquence, ex. TURBO_5 à 1/1602) ;
- seed, versions de code et de règle épinglées dans
  `research.prospective_cohorts`.

**Un résultat positif sur 45 jours ne prouvera jamais une rentabilité
durable** — la variance à P=1/4005 fait qu'un seul gain (probabilité ~1 %
sous le nul) suffirait à afficher un ROI positif. Toute conclusion exige la
poursuite prospective au-delà de l'horizon ou une puissance recalculée sur
un pari plus fréquent.

Aucune activation n'est proposée ni effectuée à ce stade.
