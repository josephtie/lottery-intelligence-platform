-- 0026_widen_agent_roi.sql
-- Un gain Turbo/5N (cote 40000 x 100 = 4 000 000) fait déborder le ROI cumulé
-- au-delà de NUMERIC(10,6) (max 9999.999999). Élargit roi à NUMERIC(15,6).
-- La vue agent_summary référence roi : on la drop puis la recrée.
DROP VIEW IF EXISTS edge_lab.agent_summary;

ALTER TABLE edge_lab.agent_capital
    ALTER COLUMN roi TYPE NUMERIC(15,6);

CREATE VIEW edge_lab.agent_summary AS
SELECT
    a.agent_id,
    a.code,
    a.display_name,
    a.generation,
    a.status,
    a.operational_level,
    a.mission,
    ac.initial_capital,
    ac.current_capital,
    ac.net_profit,
    ac.roi,
    ac.total_bets,
    ac.winning_bets,
    ac.losing_bets,
    ac.no_bet_count,
    ac.max_drawdown,
    (SELECT COUNT(*) FROM edge_lab.memory_experiments WHERE agent_id = a.agent_id) AS experiments_count,
    (SELECT COUNT(*) FROM edge_lab.memory_hypotheses WHERE agent_id = a.agent_id) AS hypotheses_count,
    (SELECT COUNT(*) FROM edge_lab.memory_successes WHERE agent_id = a.agent_id) AS successes_count,
    (SELECT COUNT(*) FROM edge_lab.memory_failures WHERE agent_id = a.agent_id) AS failures_count,
    (SELECT content FROM edge_lab.agent_reflections WHERE agent_id = a.agent_id AND reflection_type = 'POST_SETTLEMENT' ORDER BY created_at DESC LIMIT 1) AS last_reflection,
    a.created_at AS agent_created_at,
    ac.last_updated_at AS capital_updated_at
FROM edge_lab.agents a
LEFT JOIN edge_lab.agent_capital ac ON ac.agent_id = a.agent_id;
