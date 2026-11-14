#!/usr/bin/env python3
"""Add calling image models to the prospective cohort for automatic predictions."""

import psycopg
from lottery_intelligence_platform.prediction_generation import (
    register_lab_cohort,
    ensure_default_cohort,
)

def main():
    # Connect to database
    dsn = "dbname=lottery_platform user=directus password=directus host=localhost port=5432"
    
    with psycopg.connect(dsn) as conn:
        print("=== Adding Calling Image models to prospective cohort ===\n")
        
        # Ensure default cohort exists
        print("1. Ensuring default cohort exists...")
        ensure_default_cohort(conn)
        print("   ✓ Default cohort exists\n")
        
        # Register lab models (including calling image)
        print("2. Registering lab models (including calling image)...")
        result = register_lab_cohort(conn, cohort_code="prospective_turbo_v1")
        print(f"   Registered models: {result['registered']}")
        print(f"   Cohort version created: {result['cohort_version_created']}\n")
        
        # Check which calling image models are now in the cohort
        print("3. Checking calling image models in cohort...")
        latest_version = conn.execute(
            """SELECT cohort_version_id 
               FROM research.prospective_cohort_versions 
               WHERE cohort_id = (SELECT cohort_id FROM research.prospective_cohorts WHERE code = %s)
               ORDER BY version DESC LIMIT 1""",
            ("prospective_turbo_v1",)
        ).fetchone()
        
        if latest_version:
            version_id = latest_version[0]
            # Get all lab models in the cohort
            lab_models = conn.execute(
                """SELECT mv.code, mv.family, m.parameters
                   FROM research.prospective_cohort_members m
                   JOIN research.model_versions mv ON mv.model_version_id = m.model_version_id
                   WHERE m.cohort_version_id = %s
                   ORDER BY mv.code""",
                (version_id,)
            ).fetchall()
            
            # Filter for calling image, digital root, and consensus models
            calling_models = [
                (code, family, params)
                for code, family, params in lab_models
                if any(keyword in code for keyword in ["calling", "image", "digital_root", "consensus"])
            ]
            
            print(f"   Calling image models in cohort ({len(calling_models)}):")
            for code, family, params in calling_models:
                print(f"   - {code} ({family})")
                if params:
                    print(f"     Parameters: {params}")
        else:
            print("   ⚠ No cohort version found")
        
        print("\n=== Complete ===")
        print("\nNext steps:")
        print("1. Run automatic generation: .venv/bin/python -m lottery_intelligence_platform.orchestrator_cli generate_predictions")
        print("2. Check cron schedule: crontab -l")
        print("3. Monitor generation: docker compose logs -f api")

if __name__ == "__main__":
    main()
