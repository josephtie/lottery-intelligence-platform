# Matrice de migration — modules legacy → plateforme actuelle

Audit des modules de `lottery-statistics-expert-/models/` non portés.
Référence de vérité : la plateforme actuelle (`lottery-intelligence-platform`).
**Aucune intégration effectuée — recommandations seulement.**

Dépendances communes du legacy à éliminer en cas de portage :
`sqlite3` + `data/lotobonheur.sqlite3`, tables `draws`/`draw_numbers`/
`predictions`/`prediction_provenance`, `sys.path.insert` vers
`scripts/`/`models/`, tables de cotes codées en dur.

## Matrice

| Module | Rôle | Équivalent actuel | Différences | Risque | Valeur ajoutée | Décision |
|---|---|---|---|---|---|---|
| `coverage_optimizer.py` | simulateur (portefeuilles) | `lab_coverage.py` (M10) | legacy : P(≥1 grille) exacte/MC, appariement disjoint garanti, EV par pari, tous types de paris ; M10 : métriques de couverture seules, API/console | faible (hors-ligne, pas de fuite possible) | calcul exact de P(≥1 gagnante), lecture économique | **MERGE** — voir `COVERAGE_OPTIMIZER_AUDIT.md` |
| `turbo2_engine.py` | orchestrateur d'expérience | `prospective_cohorts` + `settle_pending_draws` + scheduler | legacy : scellement de décisions, protocole gelé par hash, scoring as-of, rapport J+45 immuable ; actuel : cohortes génériques versionnées | moyen (SQLite, schéma propre, migrations v24) | mécanique pré-enregistrée complète, comparateurs figés au scellement | **REIMPLEMENT** sur le moteur de cohortes |
| `turbo2_selector.py` / `turbo2_decision.py` | évaluateur + gate | vote d'ensemble (`ensemble_v1` Borda), pas de gate de pari | legacy : vote de paires inter-modèles, NO_BET sur ex æquo, gate à ~20 conditions, qualité explicitement non-probabiliste | faible | sélection par consensus de paires + gate vérifiable | **MERGE** — composants dans un futur mode « décision de pari » |
| `turbo2_historical_lab.py` | évaluateur walk-forward | walk-forward générique (matrice 4 niveaux) | legacy : balayage de seuil 1–9 dev/OOS, FDR, puissance, refus d'auto-sélection, manifeste de sources hashé | faible | protocole de calibration de gate OOS exemplaire | **MERGE** — gabarit pour évaluer tout seuil de décision |
| `bet_economics.py` | évaluateur économique | `settlement.py` (Turbo seulement) + `risk_evaluation.py` | legacy : EV/ROI/drawdown pour les 15 types de paris, cotes DC en tuple ; actuel : settlement Turbo uniquement, autres types non réglés | moyen — table `ODDS_LONACI` codée en dur à remplacer par `catalog.payout_rule_versions` | économie multi-paris, drawdown sur séquence réelle | **MERGE** — après versionnage des règles kN/PN/DC |
| `bet_scoring.py` | évaluateur (scoring multi-paris) | `settlement.py` : Turbo positionnel uniquement | legacy : kN officiel (k numéros choisis, C(5,k)/C(90,k)), PN position 1, DC avec machines ; conventions dérivées documentées | moyen — nécessite `machine_numbers` (présents en base : `number_role='MACHINE'`, 69 605 lignes) | scoring kN/PN/DC — **comble un vrai trou** : la plateforme ne règle que Turbo | **REIMPLEMENT** — scoring + baselines dans `settlement.py`/`payout_rule_versions`, avec source officielle par type |
| `null_reference.py` | évaluateur (références nulles) | `structure_analysis.null_reference` (χ² sur fréquences simulées) | legacy : 3 dispositifs — oracle théorique par pari (EV, intervalles de fluctuation, seuils de détection 1 %), **permutation par numéro du modèle en walk-forward** (le vrai M04 : le modèle testé contre un historique à marges identiques mais ordre détruit), batterie sérielle (runs test, autocorr lag1/2, taux de répétition) | faible | la permutation au niveau **modèle** est le garde-fou M04 le plus fort — l'actuel ne permute que les fréquences, pas la performance du modèle | **MERGE** — porter `permutation_null` et la batterie sérielle dans `structure_analysis.py` |
| `structure_lab.py` | évaluateur (structure) | `structure_analysis.serial_dependence` + `drift.detect_change_point` (M05/M06) | legacy : transitions Markov par position, transitions de catégories (médiane), walk-forward « jouer t−1 », CUSUM sommes (k=0,5σ/h=5σ), χ² moitiés 178 ddl ; actuel : overlap + χ² 2×2, rupture mensuelle par permutation | faible | CUSUM sur les sommes = détecteur complémentaire au χ² mensuel ; test « jouer t−1 » = vérification économique directe de la dépendance | **MERGE** — CUSUM + markov par position + test jouer-t−1 |
| `calibration_lab.py` | évaluateur (calibration) | `calibration.py` / `calibration_evaluation.py` | legacy : Brier/log-loss/ECE par numéro via mapping rang→probabilité normalisé Σ=5 ; actuel : calibration déjà câblée dans l'évaluation des modèles | faible | la convention de scoring rang→probabilité est arbitraire ; l'ECE 10 bins par numéro est un détail utile | **DEFER** — redondance partielle ; revoir uniquement si la calibration actuelle est jugée insuffisante |
| `expert_engine.py` | reporting / orchestrateur de rapports | `weekly_research_report` + console | legacy : briefing d'analyste unifié (données, modèles, positions, calibration, économie, registre d'exécution des composants avec fraîcheur/échecs) ; actuel : rapport hebdo orienté suspensions + vues séparées | faible | le **registre d'exécution des composants** (exécuté ? quand ? échec ?) — le meta-monitoring des analyses, partiellement couvert par `ops.job_runs` | **DEFER** — un tableau de bord « santé des analyses » dans la console couvrirait l'essentiel |
| `prospective_report.py` | évaluateur + reporting | `ProspectiveH008.vue` + `/api/prospective/*` + coverage ledger | legacy : validation des empreintes intégrité + provenance par cellule, comptabilisation des raisons d'exclusion, scoring par type de pari (incl. DC), coupure `collected_at ≤ as_of` | faible | l'**inventaire des raisons d'exclusion** et le flag de provenance incomplète par cellule sont plus riches que le ledger actuel | **MERGE** — enrichir le coverage ledger : raisons d'exclusion + statut de provenance |
| `turbo2_45d_protocol.json` | protocole (spec) | gabarit de cohorte pré-enregistrée | spec papier complète (voir `TURBO2_45D_AUDIT.md`) ; jamais activée, snapshots de règles non épinglés | faible | structure de protocole exemplaire | **NEEDS_RESEARCH** — trame pour `prospective_turbo2_45d_v1` |

## Non classés mais présents

`turbo2_report.py` (rapport J+45) : `REJECT_DUPLICATE` — fonction couverte par
les rapports de cohorte. `models.py` (registre des 9 modèles H008) : les 9
pickers sont déjà portés — `REJECT_DUPLICATE`.

## Tests legacy existants

`test_bet_scoring.py`, `test_integration.py`, `test_null_reference_reporting.py`,
`test_pn_dc_scoring.py`, `test_prospective_report.py`, `test_structure_coverage.py`,
`test_turbo2_engine.py`, `test_turbo2_historical_lab.py`, `test_turbo2_selector.py`,
`test_turbo_scoring.py` — couverture correcte des modules prioritaires. Tout
portage doit réécrire ces tests sur le schéma PostgreSQL.

## Fuites temporelles — résultat global

Aucune fuite détectée dans les modules audités : walk-forward strict
(`draws[:i]`), scellement vérifié par `history_max_draw_id`, comparateurs
seedés figés au moment de la décision, scoring avec coupure `as_of`,
split dev/OOS non utilisé pour sélectionner des seuils.

## Hypothèses à ne pas réintroduire

- `ODDS_LONACI` / `ODDS` / `MISE` codés en dur → `catalog.payout_rule_versions`
  versionné + source.
- SQLite et les tables ad-hoc (`turbo2_decisions`, `turbo2_protocols`,
  `predictions` legacy) → schéma `core.`/`research.`/`prospective.*`.
- Le label `H008` et `MIN_DRAWS` de `analyze.py` → paramètres de cohorte.
- Les DC : basés sur une approximation d'union `P(g)+P(m)(1−P(g))`
  explicitement documentée comme conservative — à recalculer sur les
  `machine_numbers` réels avant toute activation.

## Synthèse

**Déjà couvert** : fréquences, retards, paires+FDR, walk-forward, ensemble,
settlement Turbo positionnel, Monte-Carlo bankroll, couverture (version
simple), journal scientifique, orchestration, métriques prospectives.

**Meilleur dans le legacy** : (1) le protocole Turbo-2 gelé par hash avec
gate multi-conditions — modèle de rigueur à réutiliser ; (2) la permutation
**au niveau modèle** de `null_reference.py` (vrai M04) ; (3) le calcul exact
de P(≥1 grille gagnante) de `coverage_optimizer.py` ; (4) le scoring kN/PN/DC
de `bet_scoring.py` — la plateforme ne règle actuellement que Turbo.

**À rejeter** : toute dépendance SQLite, les tables de cotes codées en dur,
les conventions dérivées présentées comme règles officielles (kN sur 5
numéros joués — le legacy documente lui-même la correction).

**Mérite une expérimentation future** : `prospective_turbo2_45d_v1`
(pré-enregistrée, sans activation automatique) ; la permutation modèle-level
comme test standard M04 ; l'économie multi-paris après versionnage des
règles kN/PN/DC.

**Peut attendre après le déploiement VPS** : tout. Aucun module legacy n'est
bloquant — la plateforme actuelle est supérieure en architecture (PostgreSQL,
cohortes versionnées, immutabilité des scellés, console). Les portages
proposés sont des enrichissements, pas des corrections.
