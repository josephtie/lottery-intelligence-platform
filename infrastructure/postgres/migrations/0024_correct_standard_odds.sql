-- ============================================================================
-- 0024 : corriger les cotes standard PN et 1N (source officielle LONACI)
-- ============================================================================
-- Source : https://www.lonaci.ci/loto_bonheur/ (et https://lotobonheur.ci)
--   PN  cote 40  (1er numéro tiré)
--   1N  cote 10  (1 numéro parmi les 5)
--   2N  cote 240 | 3N 2000 | 4N 5000 | 5N 40000  (déjà corrects)
--
-- La migration 0023 avait introduit PN=55 et 1N=11, en désaccord avec la
-- source officielle. Correction additive (UPDATE uniquement, aucune suppression).

UPDATE catalog.betting_odds
SET odds = 40
WHERE tier_code = 'PN' AND odds = 55;

UPDATE catalog.betting_odds
SET odds = 10
WHERE tier_code = '1N' AND odds = 11;
