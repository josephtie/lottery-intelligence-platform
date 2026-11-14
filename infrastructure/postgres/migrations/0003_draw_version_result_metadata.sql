ALTER TABLE core.draw_versions
    ADD COLUMN result_metadata JSONB NOT NULL DEFAULT '{}'::JSONB;
