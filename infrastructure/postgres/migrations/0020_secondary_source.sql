-- Secondary (independent) source observations and reconciliation.
--
-- The platform's only source is lotobonheur.ci. An independent check requires
-- a second source. Since no second URL is known, the channel is a file import:
-- observations exported from any independent record (aggregator, PDF, manual
-- transcription) are loaded, preserved raw, and reconciled against the
-- canonical registry. Conflicts are recorded and alerted — never auto-applied.

INSERT INTO ingestion.sources
    (source_id, code, display_name, base_uri, source_kind, is_active)
VALUES
    (gen_random_uuid(), 'lotobonheur_secondary', 'LotoBonheur independent check',
     'file://secondary', 'FILE', true)
ON CONFLICT (code) DO NOTHING;

-- Raw observations as received from the independent source (append-only).
CREATE TABLE ingestion.secondary_observations (
    observation_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id           UUID NOT NULL REFERENCES ingestion.sources (source_id),
    raw_object_id       UUID NOT NULL REFERENCES ingestion.raw_objects (raw_object_id),
    draw_date           DATE NOT NULL,
    draw_name           TEXT NOT NULL,
    winning_numbers     INTEGER[] NOT NULL,
    machine_numbers     INTEGER[],
    payload             JSONB NOT NULL,
    imported_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_id, draw_date, draw_name)
);

-- Reconciliation verdicts (append-only; a re-run inserts a fresh row).
CREATE TABLE ingestion.source_comparisons (
    comparison_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    observation_id      UUID NOT NULL REFERENCES ingestion.secondary_observations (observation_id),
    draw_id             UUID REFERENCES core.draws (draw_id),
    outcome             TEXT NOT NULL CHECK (outcome IN (
                            'MATCH', 'MISMATCH', 'MISSING_PRIMARY', 'UNMATCHED_NAME')),
    primary_numbers     INTEGER[],
    secondary_numbers   INTEGER[],
    detail              JSONB NOT NULL DEFAULT '{}',
    compared_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX source_comparisons_observation_idx
    ON ingestion.source_comparisons (observation_id, compared_at DESC);
