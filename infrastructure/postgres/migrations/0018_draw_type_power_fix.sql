-- Fix draw_type_power: draw types exist once per game_version (the superseded
-- provisional version created duplicate rows), so power statistics must be
-- grouped by display_name across all draw_type_ids of that name, not per id.
-- Both views are dropped and recreated because the key column changes.

DROP VIEW IF EXISTS research.prospective_metrics;
DROP VIEW IF EXISTS research.draw_type_power;

CREATE VIEW research.draw_type_power AS
SELECT
    dt.display_name,
    COUNT(d.draw_id) FILTER (WHERE d.status IN ('FROZEN', 'SETTLED')) AS settled_draws,
    MIN(d.scheduled_date) FILTER (WHERE d.status IN ('FROZEN', 'SETTLED')) AS first_draw,
    COUNT(d.draw_id) FILTER (WHERE d.status IN ('FROZEN', 'SETTLED')) >= 30 AS meets_power_threshold
FROM catalog.draw_types dt
LEFT JOIN core.draws d ON d.draw_type_id = dt.draw_type_id
GROUP BY dt.display_name;

CREATE VIEW research.prospective_metrics AS
WITH base AS (
    SELECT
        cv.cohort_version_id,
        c.code AS cohort_code,
        cv.version AS cohort_version,
        cv.effective_from,
        mv.code AS model_code,
        dt.display_name AS draw_type,
        cov.status AS coverage_status,
        cov.reason,
        p.status AS prediction_status,
        o.hit_count,
        o.positional_hits,
        o.metrics AS outcome_metrics
    FROM research.prediction_coverage cov
    JOIN research.prospective_cohort_versions cv
      ON cv.cohort_version_id = cov.cohort_version_id
    JOIN research.prospective_cohorts c ON c.cohort_id = cv.cohort_id
    JOIN research.model_versions mv ON mv.model_version_id = cov.model_version_id
    JOIN catalog.draw_types dt ON dt.draw_type_id = cov.draw_type_id
    LEFT JOIN research.predictions p ON p.prediction_id = cov.prediction_id
    LEFT JOIN research.prediction_outcomes o ON o.prediction_id = p.prediction_id
),
agg AS (
    SELECT
        cohort_version_id, cohort_code, cohort_version, effective_from,
        model_code, draw_type,
        COUNT(*) AS eligible_pairs,
        COUNT(*) FILTER (WHERE coverage_status = 'GENERATED') AS generated,
        COUNT(*) FILTER (WHERE coverage_status = 'MISSING') AS missing,
        COUNT(*) FILTER (WHERE coverage_status = 'FAILED') AS failed,
        COUNT(*) FILTER (WHERE coverage_status = 'INELIGIBLE') AS ineligible,
        COUNT(*) FILTER (
            WHERE coverage_status IN ('MISSING', 'FAILED', 'INELIGIBLE')
        ) AS absent_total,
        COUNT(*) FILTER (WHERE prediction_status = 'PENDING') AS pending,
        COUNT(*) FILTER (WHERE prediction_status = 'LOCKED') AS locked,
        COUNT(*) FILTER (WHERE prediction_status = 'INVALID') AS invalid,
        COUNT(hit_count) AS settled,
        AVG(hit_count)::numeric(10, 4) AS mean_hits,
        SUM((positional_hits ->> 'first_1')::int) AS hits_first_1,
        SUM((positional_hits ->> 'first_2')::int) AS hits_first_2,
        SUM((positional_hits ->> 'first_3')::int) AS hits_first_3,
        SUM((positional_hits ->> 'first_4')::int) AS hits_first_4,
        SUM((positional_hits ->> 'first_5')::int) AS hits_first_5
    FROM base
    GROUP BY cohort_version_id, cohort_code, cohort_version, effective_from,
             model_code, draw_type
),
turbo_flat AS (
    SELECT
        b.cohort_version_id, b.model_code, b.draw_type,
        t.variant,
        COUNT(*) AS bets,
        COUNT(*) FILTER (WHERE (t.val ->> 'hit')::boolean) AS hits,
        SUM((t.val ->> 'stake')::numeric) AS stake,
        SUM((t.val ->> 'payout')::numeric) AS payout,
        SUM((t.val ->> 'net')::numeric) AS net
    FROM base b
    CROSS JOIN LATERAL jsonb_each(b.outcome_metrics -> 'turbo') AS t(variant, val)
    WHERE b.outcome_metrics IS NOT NULL
    GROUP BY b.cohort_version_id, b.model_code, b.draw_type, t.variant
),
turbo_json AS (
    SELECT
        cohort_version_id, model_code, draw_type,
        jsonb_object_agg(
            variant,
            jsonb_build_object(
                'bets', bets,
                'hits', hits,
                'stake', stake,
                'payout', payout,
                'net', net,
                'roi', ROUND(net / NULLIF(stake, 0), 6)
            )
        ) AS turbo
    FROM turbo_flat
    GROUP BY cohort_version_id, model_code, draw_type
)
SELECT
    a.cohort_code,
    a.cohort_version,
    a.cohort_version_id,
    a.effective_from,
    a.model_code,
    a.draw_type,
    a.eligible_pairs,
    a.generated,
    a.missing,
    a.failed,
    a.ineligible,
    a.absent_total,
    a.pending,
    a.locked,
    a.invalid,
    a.settled,
    ROUND(a.settled::numeric / NULLIF(a.generated, 0), 6) AS settlement_rate,
    a.mean_hits,
    COALESCE(a.hits_first_1, 0) AS hits_first_1,
    COALESCE(a.hits_first_2, 0) AS hits_first_2,
    COALESCE(a.hits_first_3, 0) AS hits_first_3,
    COALESCE(a.hits_first_4, 0) AS hits_first_4,
    COALESCE(a.hits_first_5, 0) AS hits_first_5,
    COALESCE(t.turbo, '{}'::jsonb) AS turbo,
    p.settled_draws AS historical_draws,
    NOT COALESCE(p.meets_power_threshold, false) AS low_power
FROM agg a
LEFT JOIN turbo_json t
  ON t.cohort_version_id = a.cohort_version_id
 AND t.model_code = a.model_code
 AND t.draw_type = a.draw_type
LEFT JOIN research.draw_type_power p ON p.display_name = a.draw_type;
