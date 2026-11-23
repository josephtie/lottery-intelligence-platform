# Digital Root Statistics — documentation des calculs et limites

Module `src/lottery_intelligence_platform/digital_root_statistics.py`, exposé par
`GET /api/digital-root-statistics?draw_type=<nom>&reference_date=<YYYY-MM-DD>`,
affiché dans l'onglet « Racines numériques » de la vue **Statistiques par jeu**.

## 1. Convention de calcul

La racine numérique d'un numéro est la somme récursive de ses chiffres réduite à
un chiffre, avec la **racine 9 représentée par 0** (voir `digital_root.py`).

- 74 → 2, 84 → 3, 12 → 3, 29 → 2, 10 → 1, 45 → 0, 86 → 5.
- Il en résulte **9 classes : 0 à 8** (pas de 10e classe « 9 »).

Chaque classe couvre exactement **10 numéros sur 90**, donc la **référence
uniforme** vaut `10/90 ≈ 11,111 %` par classe — y compris **par position**, car
chaque position tire dans le même univers 1..90.

## 2. Fenêtres temporelles

Cinq fenêtres calendaires **imbriquées** : 10, 30, 45, 60 et 90 jours.

- Borne **inclusive** des deux côtés : `[référence − N jours, référence]`.
- La **date de référence** est `reference_date` (défaut : date du jour, fuseau
  `Africa/Abidjan`). Tout tirage **postérieur** à la référence est exclu.
- On compte des **jours calendaires réels**, jamais un nombre arbitraire de tirages.
- Le nombre de tirages et de numéros analysés est affiché pour chaque fenêtre.

## 3. Analyses produites

| Analyse | Contenu |
|---|---|
| Distribution globale | par racine 0–8 : occurrences, % des numéros, tirages contenant la racine, écart à 11,111 % (points). |
| Distribution par position | par position 1–5 : occurrences et % de chaque racine, racine dominante. |
| Signatures | par tirage : numéros, signature des racines, nombre de racines distinctes, répétitions, date. |
| Familles | par racine : la liste des 10 numéros candidats, occurrences, fréquence par position. |
| Transitions | matrice 9×9 racine→racine entre tirages successifs + fréquences conditionnelles (normalisées par racine d'origine). |
| Évolution | comparaison des 5 fenêtres imbriquées : racine dominante, part, tirages, variation en points. |
| Qualité | doublons (même date + numéros), dates invalides (futures), trous de dates, volume par fenêtre. |
| Walk-forward | prédit la racine suivante par le **mode** de la fenêtre strictement antérieure, comparé au hasard uniforme (1/9). |

## 4. Validation walk-forward

Chronologique et **sans regard vers le futur** : pour chaque tirage `i`, la racine
prédite (par position) est le mode des racines des tirages `[i−N, i−1]`. Le score
est le taux de coïncidence, comparé à la référence aléatoire `1/9 ≈ 11,1 %`.
Résultats séparés par position et par fenêtre.

## 5. Résultats observés (Digital 21h, 1683 tirages, référence 2026-10-25)

- Racine globale dominante : 5 (11,7 %, écart +0,6 pt — non significatif).
- Walk-forward 90 j : taux de coïncidence **10,7 %** contre 11,1 % au hasard →
  **le mode des racines ne bat pas le hasard**, cohérent avec le verdict
  statistique établi de la plateforme (aucun avantage prédictif démontré).

## 6. Limites connues

- **Fréquences passées ≠ probabilités futures.** Ce module est strictement
  **descriptif** ; aucune fréquence élevée n'est une garantie de sortie.
- Les fenêtres étant **imbriquées**, leurs résultats ne sont **pas indépendants** ;
  aucune fenêtre n'est « meilleure » parce qu'observée après coup.
- La distribution par position, les familles et les transitions sont calculées sur
  **tout l'historique** (jusqu'à la référence) ; seule la distribution globale est
  ventilée par fenêtre (via l'évolution). Ventilation fine par fenêtre = amélioration
  ultérieure.
- Le walk-forward n'évalue qu'une stratégie simple (mode par position) ; il ne
  corrige pas les comparaisons multiples (plusieurs jeux × fenêtres × positions).
  Toute extension prédictive devra documenter ses hypothèses et corriger le FDR.
- Le contrôle de qualité signale les jours sans tirage (trous) sans distinguer
  jour férié / absence de collecte / donnée réellement manquante.
- La résolution du `draw_type` retient celui qui a le **plus de tirages** lorsqu'un
  même nom existe sous plusieurs versions de jeu (2 game_versions cohabitent après
  un backfill + une collecte parallèle).
