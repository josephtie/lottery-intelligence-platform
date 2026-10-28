# Validation des racines numériques — signal ou description du passé ?

Script : `scripts/digital_root_validation.py`. Exécuté sur les données réelles de
la base (tous les jeux à ≥100 tirages réglés), référence 2026-10-25.

## Méthode

1. **Statistiques descriptives** sur les 5 fenêtres (10/30/45/60/90 j) : pour chaque
   jeu, la racine dominante, sa part et son écart à la référence uniforme (11,11 %).
2. **Prédiction walk-forward** : pour chaque tirage, on prédit la racine de la position
   suivante par le **mode** de la fenêtre strictement antérieure (aucune donnée future).
3. **Comparaison au hasard** : référence `1/9 ≈ 11,11 %`, test binomial **unilatéral
   exact** (log-gamma, sans scipy).
4. **Correction des comparaisons multiples** : FDR Benjamini-Hochberg sur l'ensemble
   des tests (jeux × fenêtres × positions), seuil `q < 0,10`.

## Résultat

- **Jeux analysés** : ~35 (≥100 tirages). **Tests** : ~1 050 (5 fenêtres × 6 séries).
- Les taux de coïncidence walk-forward oscillent autour de **11,1 %** (hasard) ;
  aucune fenêtre ni position ne dépasse durablement la référence.
- Quelques p-values isolées `< 0,05` avant correction (ex. Afterwork 30 j `p=0,005`,
  Monday Special 60 j position 3 `p=0,029`) — toutes attendues sur ~1 050 tests
  (≈53 faux positifs au seuil 5 %) et **aucune ne survit au FDR**.

## Verdict

**Aucun test ne survit au FDR.** Les racines numériques sont une **description du
passé**, pas un signal prédictif exploitable. Cohérent avec le verdict établi de la
plateforme : la fréquence (des numéros comme des racines) ne bat pas le hasard
hors échantillon.
