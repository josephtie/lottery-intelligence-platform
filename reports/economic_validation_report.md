# MISSION 3 — Rapport de validation économique du signal de fréquence

Branche `feature/fusion-audit` · source officielle : `lonaci.ci/loto_bonheur` · méthode reproductible : `scripts/economic_validation.py` (+ `reports/economic_validation.json`).

> Règle de lecture : lift en hits ≠ lift en probabilité de gain ≠ lift économique. Aucun gain n'est garanti ; aucun pari réel n'est placé.

---

## 1. Règles officielles verrouillées (source vérifiée)

Source : **https://www.lonaci.ci/loto_bonheur/** (consultée ce jour). Extrait exact :

> « Gain = Mise unitaire × Coefficient du type de pari × Nombre de combinaison(s) gagnante(s) » · « 1N côte **10** : trouver un numéro parmi les cinq premières boules tirées, quelle que soit leur position » · « 2N côte **240** » · « PN côte **40** (1er numéro) » · « 3N **2 000**, 4N **5 000**, 5N **40 000** » · « Mise unitaire 25 FCFA, prix minimum 100 FCFA ».

| Pari | Condition de gain | Cote (officielle) | P(gain) théorique | RTP = cote × P |
|---|---|---|---|---|
| 1N | 1 numéro ∈ 5 gagnants | **10** | 5/90 = 5,556 % | 55,56 % |
| 2N | 2 numéros ∈ 5 gagnants | **240** | C(5,2)/C(90,2) = 0,2497 % | 59,93 % |
| PN | numéro en position 1 | **40** | 1/90 = 1,111 % | 44,44 % |

**Anomalie corrigée** : la plateforme portait `1N = 11` et `PN = 55`, en désaccord avec la source officielle. Corrigé dans `betting_formulas.py` (1N→10, PN→40), `docs/BETTING_FORMULAS_INTEGRATION.md`, et ajout d'une migration additive `0024_correct_standard_odds.sql` (UPDATE des cotes en base). Vérification de plausibilité : pour chaque pari standard, `cote × P(gain) < 1` (test `test_rtp_below_one_all_standard`).

---

## 2. Stratégies définies AVANT le test (protocole figé)

1. **Fréquence 1N** : parier 1N (cote 10) sur le numéro le plus fréquent des **60 derniers tirages** (fenêtre unique, prédéfinie).
2. **Fréquence 2N** : parier 2N (cote 240) sur les **2 numéros les plus fréquents** des 60 derniers tirages.
3. **Référence aléatoire** : 1N et 2N sur numéros tirés uniformément, mêmes mises (100 FCFA) et mêmes cotes.
4. Aucune fusion, aucune fenêtre multiple (une seule fenêtre prévue au protocole).

Sélection **horodatée et scellée par construction** : à chaque tirage i, seuls les tirages `< i` sont utilisés (walk-forward strict). Aucune modification rétrospective.

---

## 3. Résultats économiques (walk-forward + holdout final)

**Holdout final = 200 derniers tirages**, jamais utilisés pour ajuster (le split dev/holdout est figé). Références aléatoires : 200 seeds. EV null théorique = −44,44 F (1N), −40,07 F (2N).

### Digital 21h (1 615 tirages : dev 1 415, holdout 200)

| Stratégie | phase | n | win rate | EV/pari | ROI | IC95 EV | drawdown max | p vs hasard |
|---|---|---|---|---|---|---|---|---|
| 1N fréquence | dev | 1415 | 6,93 % | −30,74 F | −30,7 % | [−44, −17] | 43 700 F | 0,020 |
| 1N aléatoire | dev | 1415 | 5,30 % | −47,00 F | −47,0 % | [−59, −35] | 66 800 F | — |
| **1N fréquence** | **holdout** | **200** | **5,00 %** | **−50,00 F** | **−50 %** | [−80, −20] | 10 000 F | **0,806** |
| 2N fréquence | dev | 1415 | 0,21 % | −49,12 F | −49,1 % | [−100, +19] | 74 700 F | 0,537 |
| 2N fréquence | holdout | 200 | 0,00 % | −100,00 F | −100 % | [−100, −100] | 20 000 F | 1,0 |

### Digital 23h (1 562 tirages : dev 1 362, holdout 200)

| Stratégie | phase | n | win rate | EV/pari | ROI | IC95 EV | drawdown max | p vs hasard |
|---|---|---|---|---|---|---|---|---|
| 1N fréquence | dev | 1362 | 6,54 % | −34,65 F | −34,6 % | [−46, −21] | 47 400 F | 0,050 |
| **1N fréquence** | **holdout** | **200** | **8,00 %** | **−20,00 F** | **−20 %** | [−55, +25] | 5 600 F | **0,005** |
| 2N fréquence | dev | 1362 | 0,37 % | −11,89 F | −11,9 % | [−82, +76] | 51 600 F | 0,229 |
| 2N fréquence | holdout | 200 | 0,50 % | +20,00 F | +20 % | [−100, +380] | 17 000 F | 0,070 |

---

## 4. Lecture des trois lifts (distinction imposée)

1. **Lift en hits** (mission 2) : +0,09 à +0,12 hit moyen — réel et reproductible.
2. **Lift en probabilité de gain** : le 1N passe de ~5,6 % (théorique) à **6,5–6,9 %** en développement — soit un lift relatif de +17 à +24 % sur la probabilité.
3. **Lift économique** : l'EV du 1N passe de −44 F (hasard) à **−31 à −35 F** en développement — un gain de +10 à +14 F/pari, mais **toujours négatif**.

**Le lift économique est réel mais insuffisant de plusieurs ordres de grandeur** :
- Pour être EV+ au **1N** (cote 10), il faudrait un win rate **> 10 %**, soit +80 % de lift relatif supplémentaire par rapport au 6,9 % observé.
- Pour être EV+ au **2N** (cote 240), il faudrait un win rate **> 0,4167 %**, soit un doublement du 0,21–0,37 % observé.

---

## 5. Robustesse

- **Stabilité temporelle** : le lift du 1N fréquence **persiste sur le holdout de Digital 23h** (p=0,005, win 8 % vs 2,5 % aléatoire) mais **disparaît sur Digital 21h** (p=0,806, retombe à 5 %). Un signal qui survit sur un jeu mais pas sur l'autre est fragile.
- **Dépendance à une courte série** : le 2N est dominé par 0–1 gain sur 200–1 400 paris → IC95 gigantesque [−100, +380] F. **Inconcluable**.
- **Précision** : sur le holdout (n=200), l'IC95 de l'EV du 1N traverse largement zéro ([−55, +25]) → impossible de distinguer une espérance positive de zéro sur cette taille d'échantillon.
- **Absence de significativité ≠ preuve d'absence d'effet** : le lift du 1N en développement (p=0,02 à 0,05) est réel, mais il ne se traduit pas en rentabilité et ne se réplique pas de façon stable.

---

## 6. Tests automatisés

`tests/unit/test_economic_validation.py` (6 tests) :
- cotes officielles 1N=10, 2N=240, PN=40 ;
- cas limites de paiement 1N (match exact → +900 F ; miss → −100 F) ;
- cas limites de paiement 2N (2 matchs → +23 900 F ; 1 match → −100 F, match partiel non rémunéré) ;
- plausibilité RTP : `cote × P(gain) < 1` pour tous les paris standard ;
- FDR sur p-values économiques.

**Suite totale sur la branche : 22 tests verts** (fusion 5, adaptatif/formules 7, FDR 4, économique 6).

---

## 7. Conclusion

**AVANTAGE ÉCONOMIQUE NON DÉMONTRÉ.**

Le signal de fréquence détecté en mission 2 **améliore réellement l'espérance de gain nette** (le 1N passe de −44 F à ~−31 F en développement), mais :
1. l'EV reste **largement négative** (RTP ~69 % au mieux, contre 100 % requis pour l'équilibre) ;
2. le lift ne **survit pas au holdout** sur Digital 21h, et ne survit que sur un échantillon trop petit pour conclure sur Digital 23h ;
3. le 2N est **inconcluable** (variance dominante).

**La réponse au critère de réussite** : le signal de fréquence améliore le nombre moyen de numéros retrouvés, et produit un léger gain d'EV, mais **ne suffit pas à rendre le pari rentable** face au RTP structurel LONACI (~60 %). Aucun avantage économique exploitable n'est démontré — c'est un résultat valide, pas un échec.

**Recommandation** : ne pas engager de capital sur ce signal. Si une exploitation est envisagée un jour, elle exigerait (a) un lift de probabilité ≥ +80 % sur le 1N (introuvable par la seule fréquence), ou (b) un pari à RTP structurel plus favorable — aucun n'est offert par LONACI sur cette famille. Poursuivre la surveillance prospective des jeux digitaux (documentation du biais local) sans parier.
