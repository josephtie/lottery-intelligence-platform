-- ---------------------------------------------------------------------------
-- Fix draw_quality.missing_result: a draw counts as missing only once its
-- scheduled date has passed. Previously `winning_count = 0` flagged every
-- future/today EXPECTED draw (no version yet) as missing, so MISSING_DRAWS
-- alerts re-fired for draws that had not happened yet.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW core.draw_quality AS
WITH latest AS (
    SELECT DISTINCT ON (d.draw_id)
        d.draw_id, dv.draw_version_id, dv.validation_status
    FROM core.draws d
    LEFT JOIN core.draw_versions dv ON dv.draw_id = d.draw_id
    ORDER BY d.draw_id, dv.version_number DESC NULLS LAST
),
agg AS (
    SELECT
        n.draw_version_id,
        COUNT(*) FILTER (WHERE n.number_role = 'WINNING') AS winning_count,
        COUNT(DISTINCT n.number) FILTER (WHERE n.number_role = 'WINNING') AS distinct_winning,
        COUNT(*) FILTER (
            WHERE n.number_role = 'WINNING' AND (n.number < 1 OR n.number > 90)
        ) AS out_of_range
    FROM core.draw_numbers n
    GROUP BY n.draw_version_id
)
SELECT
    d.draw_id,
    dt.display_name AS draw_type,
    d.scheduled_date,
    d.status AS draw_status,
    l.validation_status,
    COALESCE(a.winning_count, 0) AS winning_count,
    COALESCE(a.out_of_range, 0) AS out_of_range,
    (l.draw_version_id IS NULL AND d.scheduled_date < CURRENT_DATE)
        OR (l.draw_version_id IS NOT NULL AND COALESCE(a.winning_count, 0) = 0)
        AS missing_result,
    a.winning_count IS NOT NULL AND a.winning_count <> 5 AS wrong_count,
    a.distinct_winning IS NOT NULL AND a.distinct_winning <> a.winning_count AS duplicate_number,
    COALESCE(a.out_of_range, 0) > 0 AS number_out_of_range
FROM core.draws d
JOIN catalog.draw_types dt ON dt.draw_type_id = d.draw_type_id
LEFT JOIN latest l ON l.draw_id = d.draw_id
LEFT JOIN agg a ON a.draw_version_id = l.draw_version_id;
