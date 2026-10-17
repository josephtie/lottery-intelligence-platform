-- BETTING FORMULOS - Loto Bonheur Official Betting Formulas
-- This migration creates tables to store official betting formulas,
-- odds, and payout rules for Loto Bonheur (LONACI).
-- Source: https://lotobonheur.ci/distribution-des-gains

-- ============================================================================
-- 1. BETTING FORMULAS CONFIGURATION
-- ============================================================================

CREATE TABLE catalog.betting_formulas (
    formula_id UUID PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    formula_type TEXT NOT NULL CHECK (formula_type IN ('STANDARD', 'TURBO', 'CHANCE', 'PERM')),
    description TEXT NOT NULL,
    numbers_required INTEGER NOT NULL CHECK (numbers_required > 0),
    numbers_maximum INTEGER CHECK (numbers_maximum >= numbers_required),
    unit_stake NUMERIC(10,2) NOT NULL DEFAULT 100.00 CHECK (unit_stake > 0),
    position_sensitive BOOLEAN NOT NULL DEFAULT FALSE,
    max_combinations INTEGER CHECK (max_combinations > 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (length(trim(code)) > 0),
    CHECK (length(trim(name)) > 0),
    CHECK (length(trim(description)) > 0)
);

CREATE INDEX betting_formulas_type_idx ON catalog.betting_formulas (formula_type);
CREATE INDEX betting_formulas_active_idx ON catalog.betting_formulas (is_active);

-- ============================================================================
-- 2. BETTING ODDS (TIERS)
-- ============================================================================

CREATE TABLE catalog.betting_odds (
    odd_id UUID PRIMARY KEY,
    formula_id UUID NOT NULL REFERENCES catalog.betting_formulas(formula_id) ON DELETE CASCADE,
    tier_code TEXT NOT NULL CHECK (tier_code ~ '^[0-9]+N$|^TURBO_[0-9]+$'),
    tier_name TEXT NOT NULL,
    odds NUMERIC(10,2) NOT NULL CHECK (odds > 0),
    payout_multiplier NUMERIC(10,2) NOT NULL DEFAULT 1.00 CHECK (payout_multiplier > 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (formula_id, tier_code),
    CHECK (length(trim(tier_code)) > 0),
    CHECK (length(trim(tier_name)) > 0)
);

CREATE INDEX betting_odds_formula_idx ON catalog.betting_odds (formula_id);
CREATE INDEX betting_odds_tier_idx ON catalog.betting_odds (tier_code);

-- ============================================================================
-- 3. PERM COMBINATION COSTS
-- ============================================================================

CREATE TABLE catalog.perm_combination_costs (
    cost_id UUID PRIMARY KEY,
    formula_id UUID NOT NULL REFERENCES catalog.betting_formulas(formula_id) ON DELETE CASCADE,
    numbers_selected INTEGER NOT NULL CHECK (numbers_selected > 0),
    combinations_generated INTEGER NOT NULL CHECK (combinations_generated > 0),
    cost_per_combination NUMERIC(10,2) NOT NULL CHECK (cost_per_combination > 0),
    total_cost NUMERIC(10,2) NOT NULL CHECK (total_cost > 0),
    is_standard_configuration BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (formula_id, numbers_selected)
);

CREATE INDEX perm_costs_formula_idx ON catalog.perm_combination_costs (formula_id);
CREATE INDEX perm_costs_numbers_idx ON catalog.perm_combination_costs (numbers_selected);

-- ============================================================================
-- 4. AGENT BETTING PREFERENCES
-- ============================================================================

CREATE TABLE edge_lab.agent_betting_preferences (
    preference_id UUID PRIMARY KEY,
    agent_id UUID NOT NULL REFERENCES edge_lab.agents(agent_id) ON DELETE CASCADE,
    formula_id UUID NOT NULL REFERENCES catalog.betting_formulas(formula_id),
    preferred_numbers_count INTEGER CHECK (preferred_numbers_count > 0),
    preferred_stake_ratio NUMERIC(5,4) CHECK (preferred_stake_ratio BETWEEN 0 AND 1),
    min_confidence_threshold NUMERIC(5,4) CHECK (min_confidence_threshold BETWEEN 0 AND 1),
    max_frequency_use INTEGER CHECK (max_frequency_use > 0),
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    priority INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (agent_id, formula_id)
);

CREATE INDEX agent_betting_agent_idx ON edge_lab.agent_betting_preferences (agent_id);
CREATE INDEX agent_betting_formula_idx ON edge_lab.agent_betting_preferences (formula_id);
CREATE INDEX agent_betting_enabled_idx ON edge_lab.agent_betting_preferences (is_enabled);

-- ============================================================================
-- 5. AGENT BETTING DECISIONS WITH FORMULAS
-- ============================================================================

-- Extend agent_decisions to include formula information
ALTER TABLE edge_lab.agent_decisions
    ADD COLUMN formula_id UUID REFERENCES catalog.betting_formulas(formula_id),
    ADD COLUMN formula_type TEXT,
    ADD COLUMN numbers_selected_count INTEGER,
    ADD COLUMN combinations_generated INTEGER,
    ADD COLUMN cost_per_combination NUMERIC(10,2);

CREATE INDEX agent_decisions_formula_idx ON edge_lab.agent_decisions (formula_id);

-- ============================================================================
-- 6. BETTING OUTCOMES WITH FORMULA CALCULATIONS
-- ============================================================================

-- Extend decision_outcomes to include formula-specific calculations
ALTER TABLE edge_lab.decision_outcomes
    ADD COLUMN tier_achieved TEXT,
    ADD COLUMN winning_combinations INTEGER DEFAULT 1,
    ADD COLUMN gain_per_combination NUMERIC(15,2),
    ADD COLUMN formula_roi NUMERIC(10,6);

-- ============================================================================
-- 7. INSERT OFFICIAL FORMULAS (from lotobonheur.ci)
-- ============================================================================

-- Standard formulas
INSERT INTO catalog.betting_formulas (formula_id, code, name, formula_type, description, numbers_required, unit_stake) VALUES
    (gen_random_uuid(), 'PN', 'Prédiction Numérique', 'STANDARD', 'Parier sur 1 numéro exact', 1, 100),
    (gen_random_uuid(), '1N', '1 Numéro', 'STANDARD', 'Parier sur 1 numéro gagnant', 1, 100),
    (gen_random_uuid(), '2N', '2 Numéros', 'STANDARD', 'Parier sur 2 numéros gagnants', 2, 100),
    (gen_random_uuid(), '3N', '3 Numéros', 'STANDARD', 'Parier sur 3 numéros gagnants', 3, 100),
    (gen_random_uuid(), '4N', '4 Numéros', 'STANDARD', 'Parier sur 4 numéros gagnants', 4, 100),
    (gen_random_uuid(), '5N', '5 Numéros', 'STANDARD', 'Parier sur 5 numéros gagnants', 5, 100);

-- Turbo formulas
INSERT INTO catalog.betting_formulas (formula_id, code, name, formula_type, description, numbers_required, unit_stake, position_sensitive) VALUES
    (gen_random_uuid(), 'TURBO_2', 'Turbo 2', 'TURBO', '2 numéros doivent être les 2 premières boules dans l''ordre', 2, 100, TRUE),
    (gen_random_uuid(), 'TURBO_3', 'Turbo 3', 'TURBO', '3 numéros doivent être les 3 premières boules dans l''ordre', 3, 100, TRUE),
    (gen_random_uuid(), 'TURBO_4', 'Turbo 4', 'TURBO', '4 numéros doivent être les 4 premières boules dans l''ordre', 4, 100, TRUE),
    (gen_random_uuid(), 'TURBO_5', 'Turbo 5', 'TURBO', '5 numéros doivent être les 5 premières boules dans l''ordre', 5, 100, TRUE);

-- Chance formulas
INSERT INTO catalog.betting_formulas (formula_id, code, name, formula_type, description, numbers_required, unit_stake) VALUES
    (gen_random_uuid(), 'CHANCE_3_PLUS', 'Chance 3+', 'CHANCE', 'Choisir 3 numéros, gains selon paliers 2N ou 3N', 3, 100),
    (gen_random_uuid(), 'CHANCE_4_PLUS', 'Chance 4+', 'CHANCE', 'Choisir 4 numéros, gains selon paliers 2N, 3N ou 4N', 4, 100),
    (gen_random_uuid(), 'CHANCE_5_PLUS', 'Chance 5+', 'CHANCE', 'Choisir 5 numéros, gains selon paliers 2N, 3N, 4N ou 5N', 5, 100);

-- PERM formulas
INSERT INTO catalog.betting_formulas (formula_id, code, name, formula_type, description, numbers_required, numbers_maximum, unit_stake, max_combinations) VALUES
    (gen_random_uuid(), 'PERM_2', 'Permutation 2', 'PERM', 'Générer toutes les paires possibles à partir de numéros choisis', 2, 90, 100, 4005),
    (gen_random_uuid(), 'PERM_3', 'Permutation 3', 'PERM', 'Générer tous les triplets possibles à partir de numéros choisis', 3, 90, 100, 117480);

-- ============================================================================
-- 8. INSERT OFFICIAL ODDS
-- ============================================================================

-- Standard odds
INSERT INTO catalog.betting_odds (odd_id, formula_id, tier_code, tier_name, odds)
SELECT gen_random_uuid(), bf.formula_id, v.tier_code, v.tier_name, v.odds_value
FROM catalog.betting_formulas bf
CROSS JOIN (
    VALUES
        ('PN', 'PN', 55),
        ('1N', '1N', 11),
        ('2N', '2N', 240),
        ('3N', '3N', 2000),
        ('4N', '4N', 5000),
        ('5N', '5N', 40000)
) AS v(tier_code, tier_name, odds_value)
WHERE bf.code = v.tier_code AND bf.formula_type = 'STANDARD';

-- Turbo odds
INSERT INTO catalog.betting_odds (odd_id, formula_id, tier_code, tier_name, odds)
SELECT gen_random_uuid(), bf.formula_id, v.tier_code, v.tier_name, v.odds_value
FROM catalog.betting_formulas bf
CROSS JOIN (
    VALUES
        ('TURBO_2', 'Turbo 2', 2400),
        ('TURBO_3', 'Turbo 3', 800),
        ('TURBO_4', 'Turbo 4', 400),
        ('TURBO_5', 'Turbo 5', 240)
) AS v(tier_code, tier_name, odds_value)
WHERE bf.code = v.tier_code AND bf.formula_type = 'TURBO';

-- Chance odds
INSERT INTO catalog.betting_odds (odd_id, formula_id, tier_code, tier_name, odds)
SELECT gen_random_uuid(), bf.formula_id, v.tier_code, v.tier_name, v.odds_value
FROM catalog.betting_formulas bf
CROSS JOIN (
    VALUES
        ('CHANCE_3_PLUS', '2N', 60),
        ('CHANCE_3_PLUS', '3N', 1750),
        ('CHANCE_4_PLUS', '2N', 30),
        ('CHANCE_4_PLUS', '3N', 300),
        ('CHANCE_4_PLUS', '4N', 10000),
        ('CHANCE_5_PLUS', '2N', 20),
        ('CHANCE_5_PLUS', '3N', 100),
        ('CHANCE_5_PLUS', '4N', 2000),
        ('CHANCE_5_PLUS', '5N', 50000)
) AS v(formula_code, tier_code, odds_value)
WHERE bf.code = v.formula_code AND bf.formula_type = 'CHANCE';

-- PERM odds
INSERT INTO catalog.betting_odds (odd_id, formula_id, tier_code, tier_name, odds)
SELECT gen_random_uuid(), bf.formula_id, v.tier_code, v.tier_name, v.odds_value
FROM catalog.betting_formulas bf
CROSS JOIN (
    VALUES
        ('PERM_2', '2N', 240),
        ('PERM_3', '3N', 2000)
) AS v(formula_code, tier_code, odds_value)
WHERE bf.code = v.formula_code AND bf.formula_type = 'PERM';

-- ============================================================================
-- 9. INSERT STANDARD PERM CONFIGURATIONS
-- ============================================================================

-- PERM 2 standard configurations (3-10 numbers)
INSERT INTO catalog.perm_combination_costs (cost_id, formula_id, numbers_selected, combinations_generated, cost_per_combination, total_cost, is_standard_configuration)
SELECT gen_random_uuid(), bf.formula_id, v.numbers, v.combinations, v.cost_per_comb, v.total_cost, TRUE
FROM catalog.betting_formulas bf
CROSS JOIN (
    VALUES
        (3, 3, 33.33, 100),
        (4, 6, 16.67, 100),
        (5, 10, 10.00, 100),
        (6, 15, 6.67, 100),
        (7, 21, 4.76, 100),
        (8, 28, 3.57, 100),
        (9, 36, 2.78, 100),
        (10, 45, 2.22, 100)
) AS v(numbers, combinations, cost_per_comb, total_cost)
WHERE bf.code = 'PERM_2';

-- PERM 3 standard configurations (4-10 numbers)
INSERT INTO catalog.perm_combination_costs (cost_id, formula_id, numbers_selected, combinations_generated, cost_per_combination, total_cost, is_standard_configuration)
SELECT gen_random_uuid(), bf.formula_id, v.numbers, v.combinations, v.cost_per_comb, v.total_cost, TRUE
FROM catalog.betting_formulas bf
CROSS JOIN (
    VALUES
        (4, 4, 25.00, 100),
        (5, 10, 10.00, 100),
        (6, 20, 5.00, 100),
        (7, 35, 2.86, 100),
        (8, 56, 1.79, 100),
        (9, 84, 1.19, 100),
        (10, 120, 0.83, 100)
) AS v(numbers, combinations, cost_per_comb, total_cost)
WHERE bf.code = 'PERM_3';

-- ============================================================================
-- 10. VIEWS FOR AGENT USE
-- ============================================================================

-- View: Active formulas with odds
CREATE VIEW catalog.active_formulas_with_odds AS
SELECT
    bf.formula_id,
    bf.code,
    bf.name,
    bf.formula_type,
    bf.description,
    bf.numbers_required,
    bf.numbers_maximum,
    bf.unit_stake,
    bf.position_sensitive,
    bf.max_combinations,
    jsonb_agg(
        jsonb_build_object(
            'tier_code', bo.tier_code,
            'tier_name', bo.tier_name,
            'odds', bo.odds,
            'payout_multiplier', bo.payout_multiplier
        ) ORDER BY bo.tier_code
    ) AS odds,
    bf.is_active,
    bf.created_at
FROM catalog.betting_formulas bf
LEFT JOIN catalog.betting_odds bo ON bo.formula_id = bf.formula_id AND bo.is_active = TRUE
WHERE bf.is_active = TRUE
GROUP BY bf.formula_id, bf.code, bf.name, bf.formula_type, bf.description,
         bf.numbers_required, bf.numbers_maximum, bf.unit_stake,
         bf.position_sensitive, bf.max_combinations, bf.is_active, bf.created_at
ORDER BY bf.formula_type, bf.code;

-- View: Agent formula preferences
CREATE VIEW edge_lab.agent_formula_preferences AS
SELECT
    abp.agent_id,
    a.code AS agent_code,
    bf.code AS formula_code,
    bf.name AS formula_name,
    bf.formula_type,
    abp.preferred_numbers_count,
    abp.preferred_stake_ratio,
    abp.min_confidence_threshold,
    abp.max_frequency_use,
    abp.is_enabled,
    abp.priority
FROM edge_lab.agent_betting_preferences abp
JOIN edge_lab.agents a ON a.agent_id = abp.agent_id
JOIN catalog.betting_formulas bf ON bf.formula_id = bf.formula_id
WHERE abp.is_enabled = TRUE
ORDER BY abp.agent_id, abp.priority DESC;

-- View: Formula performance summary
CREATE VIEW catalog.formula_performance_summary AS
SELECT
    bf.code AS formula_code,
    bf.name AS formula_name,
    bf.formula_type,
    COUNT(ad.decision_id) AS total_decisions,
    COUNT(CASE WHEN do.outcome_type = 'WIN' THEN 1 END) AS winning_decisions,
    COUNT(CASE WHEN do.outcome_type = 'LOSE' THEN 1 END) AS losing_decisions,
    AVG(CASE WHEN do.outcome_type = 'WIN' THEN do.formula_roi END) AS avg_roi_winners,
    AVG(ad.stake_amount) AS avg_stake,
    SUM(CASE WHEN do.outcome_type = 'WIN' THEN do.net_result ELSE 0 END) AS total_profit,
    SUM(CASE WHEN do.outcome_type = 'LOSE' THEN do.net_result ELSE 0 END) AS total_loss,
    SUM(do.net_result) AS net_profit
FROM catalog.betting_formulas bf
LEFT JOIN edge_lab.agent_decisions ad ON ad.formula_id = bf.formula_id
LEFT JOIN edge_lab.decision_outcomes do ON do.decision_id = ad.decision_id
GROUP BY bf.code, bf.name, bf.formula_type
ORDER BY bf.formula_type, bf.code;

-- ============================================================================
-- 11. TRIGGERS
-- ============================================================================

-- Auto-update updated_at
CREATE FUNCTION catalog.update_formula_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER betting_formulas_update_updated_at
BEFORE UPDATE ON catalog.betting_formulas
FOR EACH ROW EXECUTE FUNCTION catalog.update_formula_updated_at();

CREATE TRIGGER betting_odds_update_updated_at
BEFORE UPDATE ON catalog.betting_odds
FOR EACH ROW EXECUTE FUNCTION catalog.update_formula_updated_at();

CREATE TRIGGER agent_betting_preferences_update_updated_at
BEFORE UPDATE ON edge_lab.agent_betting_preferences
FOR EACH ROW EXECUTE FUNCTION catalog.update_formula_updated_at();
