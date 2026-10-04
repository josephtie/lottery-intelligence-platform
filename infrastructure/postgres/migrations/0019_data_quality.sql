-- Data-quality layer (phase 05 finishers).
--
-- Three read-only views; no source data is modified. A quality score never
-- replaces anomaly detail — the flags stay per-draw/per-run and explicit.

-- Per-source daily collection quality: success rate, payload volume, and the
-- duplicate rate (re-delivered identical payloads are not errors — they are
-- idempotent re-observations, but a rising rate is a source signal).
CREATE VIEW ingestion.collection_quality AS
SELECT
    s.code AS source,
    r.started_at::date AS day,
    COUNT(*) AS runs,
    COUNT(*) FILTER (WHERE r.status = 'SUCCEEDED') AS succeeded,
    COUNT(*) FILTER (WHERE r.status = 'FAILED') AS failed,
    ROUND(
        COUNT(*) FILTER (WHERE r.status = 'SUCCEEDED')::numeric
        / NULLIF(COUNT(*), 0), 4
    ) AS success_rate,
    COUNT(e.collection_event_id) AS payloads_received,
    COUNT(DISTINCT ro.sha256) AS distinct_payloads,
    ROUND(
        1 - COUNT(DISTINCT ro.sha256)::numeric
            / NULLIF(COUNT(e.collection_event_id), 0), 4
    ) AS duplicate_rate
FROM ingestion.collection_runs r
JOIN ingestion.sources s ON s.source_id = r.source_id
LEFT JOIN ingestion.collection_events e ON e.collection_run_id = r.collection_run_id
LEFT JOIN ingestion.raw_objects ro ON ro.raw_object_id = e.raw_object_id
GROUP BY s.code, r.started_at::date;

-- Per-draw structural quality on the latest version: wrong number count,
-- duplicates inside a draw, out-of-range numbers, and draws still missing a
-- validated result past their scheduled date.
CREATE VIEW core.draw_quality AS
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
    (l.draw_version_id IS NULL AND d.status = 'EXPECTED' AND d.scheduled_date < CURRENT_DATE)
        OR COALESCE(a.winning_count, 0) = 0 AS missing_result,
    a.winning_count IS NOT NULL AND a.winning_count <> 5 AS wrong_count,
    a.distinct_winning IS NOT NULL AND a.distinct_winning <> a.winning_count AS duplicate_number,
    COALESCE(a.out_of_range, 0) > 0 AS number_out_of_range
FROM core.draws d
JOIN catalog.draw_types dt ON dt.draw_type_id = d.draw_type_id
LEFT JOIN latest l ON l.draw_id = d.draw_id
LEFT JOIN agg a ON a.draw_version_id = l.draw_version_id;

-- Rollup per draw type: anomaly counts for dashboards and alerting.
CREATE VIEW core.draw_quality_summary AS
SELECT
    draw_type,
    COUNT(*) AS draws,
    COUNT(*) FILTER (WHERE missing_result) AS missing_result,
    COUNT(*) FILTER (WHERE wrong_count) AS wrong_count,
    COUNT(*) FILTER (WHERE duplicate_number) AS duplicate_number,
    COUNT(*) FILTER (WHERE number_out_of_range) AS number_out_of_range,
    COUNT(*) FILTER (
        WHERE missing_result OR wrong_count OR duplicate_number OR number_out_of_range
    ) AS anomalous
FROM core.draw_quality
GROUP BY draw_type
ORDER BY draw_type;
