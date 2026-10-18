# MISSION 2 — Rapport : recherche d'un avantage prédictif par jeu et découverte de fusions utiles

Branche `feature/fusion-audit` · données : plateforme lottery-intelligence-platform (API `83.171.249.150:8095`) · méthode reproductible `scripts/fusion_audit.py` + `scripts/holdout_final.py`.

> Règle de lecture : anomalie détectée ≠ avantage prédictif démontré ; performance brute ≠ preuve ; absence de preuve d'uniformité ≠ preuve d'uniformité. Aucun gain futur n'est garanti.

---

## 1. Audit des métriques et des formules

**Définition exacte de `hits`** : `hits = |combinaison_sélectionnée ∩ tirage_gagnant|`, où la combinaison = 5 numéros distincts dans 1..90. Pour la référence aléatoire, on tire 5 numéros uniformément **sur les mêmes tirages**.

**Distribution nulle (hypergéométrique, 5 picks vs 5 numéros sur 90)** :

| h | P(h) |
|---|---|
| 0 | 0,7463 |
| 1 | 0,2303 |
| 2 | 0,0225 |
| 3 | 0,000812 |
| 4 | 9,7·10⁻⁶ |
| 5 | 2,3·10⁻⁸ |

- **E[hits] = 5 × 5/90 = 0,2778** (c'est ce que vaut un pick uniforme en moyenne).
- **P(≥3 hits) = P(3)+P(4)+P(5) = 0,000822 = 0,0822 % ≈ 1 tirage sur 1 217.**

**Pourquoi P(≥3) empirique = 0 sur 80 tirages (Afterwork)** : l'espérance sur 80 tirages est 80 × 0,000822 = 0,066 événement → 0 observé a une probabilité ~93,6 % sous le nul. **P(≥3)=0 sur de petits échantillons n'est pas une anomalie, c'est l'attendu.** Il faut ~1 200 tirages pour espérer un seul « ≥3 » par hasard.

**ROI −100 %** : sur les formules CHANCE_5_PLUS / 3N / PERM_2, une combinaison qui ne dépasse jamais 2 hits ne déclenche jamais de gain (3N exige 3 hits exacts). Le ROI −100 % observé est la conséquence arithmétique du faible taux de hits, **pas un bug de calcul** (vérifié par la distribution `hit_count` en base : 0/1/2 hits dominent).

**Comparaison équitable** : chaque stratégie est comparée à **200 références aléatoires équivalentes** (5 numéros uniformes, mêmes tirages), p-value par permutation unilatérale, puis correction **Benjamini-Hochberg** sur toute la famille stratégie × jeu.

---

## 2. Tableau comparatif par jeu (meilleure stratégie jouable)

| Jeu | tirages éval. | total | meilleure stratégie | hits | lift vs 0,2778 | q (FDR) | verdict |
|---|---|---|---|---|---|---|---|
| **Digital 21h** | 500 | 1675 | top_k_frequency | 0,380 | **+0,102** | **0,058** | **AVANTAGE À CONFIRMER** |
| **Digital 23h** | 500 | 1623 | top_k_frequency | 0,336 | **+0,058** | **0,058** | **AVANTAGE À CONFIRMER** |
| Digital 22h | 449 | 489 | rolling_frequency | 0,330 | +0,052 | 0,245 | compatible hasard |
| Digital Réveil 8h | 450 | 490 | hot_frequency_v1 | 0,318 | +0,040 | 0,492 | compatible hasard |
| Afterwork | 190 | 230 | random | 0,347 | +0,070 | 0,374 | compatible hasard |
| Benediction | 272 | 312 | cold_delay_v1 | 0,335 | +0,057 | 0,103 | compatible hasard |
| Cash | 271 | 311 | meta_consensus_family | 0,317 | +0,040 | 0,580 | compatible hasard |
| Espoir | 272 | 312 | cold_delay_v1 | 0,316 | +0,038 | 0,632 | compatible hasard |
| Fortune Thursday | 257 | 297 | calling_numbers | 0,319 | +0,041 | 0,632 | compatible hasard |

**Créneaux :** seuls les jeux **Digitaux** (21h/23h, et marginalement 22h/8h) portent un lift de fréquence. Les jeux « physiques » (Afterwork, Benediction, Cash, Espoir, Fortune Thursday) sont **tous compatibles avec le hasard**.

---

## 3. Classement — stratégies seules vs fusionnées

**Stratégies survivant au FDR (q < 0,10) :**

| Jeu | stratégie | hits | lift | q |
|---|---|---|---|---|
| Digital 21h | top_k_frequency / bayesian_shrinkage | 0,380 | +0,102 | 0,058 |
| Digital 21h | meta_consensus_count | 0,360 | +0,082 | 0,058 |
| Digital 21h | fusion:majority | 0,352 | +0,074 | 0,058 |
| Digital 21h | selector | 0,352 | +0,074 | 0,058 |
| Digital 21h | fusion:union | 0,348 | +0,070 | 0,058 |
| Digital 21h | balanced_v1 | 0,348 | +0,070 | 0,058 |
| Digital 23h | top_k_frequency / bayesian_shrinkage | 0,336 | +0,058 | 0,058 |

**Lecture critique** : les 7 « survivants » de Digital 21h sont **tous des modèles de fréquence ou des fusions qui l'incorporent** — c'est **un seul et même signal** (la fréquence des numéros), détecté par des stratégies corrélées, pas 7 découvertes indépendantes. Les fusions (majority/union) survivent *parce qu'elles contiennent le modèle de fréquence*, pas parce qu'elles y apportent une complémentarité démontrable.

---

## 4. Validation chronologique (holdout final, jamais utilisé pour la sélection)

Protocole : développement = tirages [0, N−200] (sélection du candidat), **holdout final = les 200 derniers tirages** (jamais vus), walk-forward pur.

| Jeu | candidat | holdout hits | lift | p (permutation) |
|---|---|---|---|---|
| Digital 21h | top_k_frequency | 0,370 | **+0,092** | 0,010 |
| Digital 23h | top_k_frequency | 0,395 | **+0,117** | 0,005 |

Le signal de fréquence **survit au holdout final** sur les deux jeux digitaux à plus fort volume, avec une réplication par moitié cohérente (21h : 0,408 / 0,352 ; 23h : 0,308 / 0,364).

**Cohérence avec l'uniformité (chi², /api/statistics)** :

| Jeu | fenêtre | χ² | df | p | uniforme |
|---|---|---|---|---|---|
| Digital 21h | 90 j | 101,6 | 89 | 0,170 | oui |
| Digital 21h | 365 j | 113,6 | 89 | **0,040** | non |
| Digital 23h | 90 j | 84,8 | 89 | 0,606 | oui |
| Digital 23h | 365 j | 109,2 | 89 | 0,072 | oui |

Le chi² global n'est significatif que pour Digital 21h sur 365 jours (p=0,040). Sur **12 tests de chi²** (6 jeux × 2 fenêtres), **un seul p<0,05 est exactement le taux de faux positif attendu (~1/12)** → le biais global n'est pas confirmé, mais le biais **local** (quelques numéros chauds) que le modèle exploite peut coexister avec un chi² global non significatif (dilution sur 89 ddl).

---

## 5. Anomalies corrigées et tests exécutés

**Anomalies de calcul corrigées (pendant la mission)** :
1. **Cherry-picking rétrospectif** dans « meilleur modèle seul » (prendre le max par tirage fuit le futur) → remplacé par un modèle fixe. (mission 1)
2. **`coverage` (union théorique ~40 numéros, injouable) proposée au sélecteur** → le sélecteur la « choisissait » (hits 1,94 → artefact). Désormais la couverture est une métrique théorique **exclue** des stratégies jouables. Le sélecteur retombe à un niveau honnête.
3. **Erreur de monotonie du FDR** : les q-values étaient tirés vers le minimum (tous à 0,058). Corrigé (min-suffix) et **testé**.

**Tests exécutés (16 verts)** :
- `tests/unit/test_fusion_engine.py` (5) — validité, capture de biais, déterminisme, walk-forward.
- `tests/unit/test_adaptive_and_formulas.py` (7) — complémentarité, formules, sélection adaptative sans fuite.
- `tests/unit/test_fdr.py` (4) — monotonie BH, bruit uniforme non rejeté, p isolé pénalisé.

---

## 6. Recommandation

**Verdict global** : les prédictions des modèles **peuvent être assemblées pour améliorer le hors-échantillon, mais le seul signal reproductible est la fréquence des numéros sur les jeux digitaux** — pas une complémentarité entre modèles. Sur Digital 21h et 23h, un modèle de fréquence simple (`top_k_frequency`) bat la référence aléatoire de +0,09 à +0,12 hit, **de façon stable et hors échantillon**. Aucune fusion ne fait mieux que le modèle de fréquence qu'elle contient déjà.

**Catégorisation finale (critères de la mission)** :
- **Avantage à confirmer** : `top_k_frequency`/`bayesian_shrinkage` sur **Digital 21h et Digital 23h**.
- **Compatible avec le hasard** : tous les jeux physiques + Digital 22h/8h.
- **≤ référence** : les modèles « anti-fréquence » (cold_delay, image) et le sélecteur sur les jeux sans signal.
- **Aucune anomalie de calcul résiduelle** détectée.

**Prochaine piste prioritaire (recommandation)** :
1. **Investir l'économie du signal de fréquence** : calculer l'EV/ROI réel du pari 1N/2N sur les numéros chauds de Digital 21h/23h avec les cotes LONACI exactes. Le lift de +0,09 hit correspond à un numéro chaud à ~7 % vs 5,56 % théorique — **à première vue insuffisant pour être EV+ face au RTP ≈ 60 %**, mais c'est le seul signal qui mérite un calcul économique dédié.
2. **Caractériser le biais** (local vs global, stationnarité) : quels numéros, depuis quand, avec quelle stabilité — via une analyse positionnelle/fréquentielle dédiée sur les deux jeux digitaux.
3. **Ne pas multiplier les agents** sur les jeux physiques (aucun signal) ; concentrer l'exploration sur les jeux digitaux.

**Aucun avantage prédictif n'est garanti** : le signal de fréquence est détecté et reproduit, mais il est local, de faible amplitude, et son exploitabilité économique reste **non démontrée**.
