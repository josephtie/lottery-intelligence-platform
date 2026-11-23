#!/usr/bin/env python3
"""Bootstrap + backfill des agents de paris fusion (capital virtuel persisté).

Usage (dans le conteneur api, qui a LOTTERY_DATABASE_* + PGPASSWORD) :
  python scripts/backfill_fusion_agents.py --bootstrap-only
  python scripts/backfill_fusion_agents.py --game "Digital 21h" --limit 200
Idempotent : une décision déjà scellée pour (agent, tirage) est sautée.
"""
import argparse
import os
import sys

import psycopg

from lottery_intelligence_platform import fusion_persistence


def dsn() -> str:
    if os.environ.get("LOTTERY_DATABASE_HOST"):
        parts = [
            f"host={os.environ['LOTTERY_DATABASE_HOST']}",
            f"port={os.environ.get('LOTTERY_DATABASE_PORT', '5432')}",
            f"dbname={os.environ.get('LOTTERY_DATABASE_NAME', 'lottery_platform')}",
            f"user={os.environ.get('LOTTERY_DATABASE_USER', 'directus')}",
        ]
        pw = os.environ.get("LOTTERY_DATABASE_PASSWORD") or os.environ.get("PGPASSWORD")
        if pw:
            parts.append(f"password={pw}")
        return " ".join(parts)
    return "host=localhost port=5432 dbname=lottery_platform user=directus"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=None, help="draw_type (display_name), ex. 'Digital 21h'")
    ap.add_argument("--limit", type=int, default=200, help="nb de tirages récents à backfill")
    ap.add_argument("--bootstrap-only", action="store_true")
    args = ap.parse_args()

    with psycopg.connect(dsn(), autocommit=True) as conn:
        if args.bootstrap_only:
            ids = fusion_persistence.bootstrap(conn)
            print(f"agents persistés : {len(ids)}")
            for code in sorted(ids):
                s = fusion_persistence.capital_summary(conn, code)
                cap = s["current_capital"] if s else "?"
                bets = s["total_bets"] if s else "?"
                print(f"  {code:24s} capital={cap}  paris={bets}")
            return 0
        result = fusion_persistence.backfill(conn, draw_type=args.game, limit=args.limit)
        print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
