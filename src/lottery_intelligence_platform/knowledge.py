"""Knowledge Engine — Hermes query interface.

Scientific memory over hypotheses, experiments and findings. Hermes (or any
research agent) uses these functions to answer "has this already been
tested?" before spending compute — rejected knowledge is as valuable as
successful knowledge.

All functions are read-only and take a psycopg connection.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping
from uuid import UUID

_WORD = re.compile(r"[a-z0-9_]+")


def _tokens(text: str) -> set[str]:
    return {t for t in _WORD.findall(text.lower()) if len(t) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def search_hypotheses(
    connection: Any, text: str, *, limit: int = 20
) -> list[dict[str, Any]]:
    """Hypotheses whose title/body lexically overlaps `text`, ranked."""
    probe = _tokens(text)
    rows = connection.execute(
        """SELECT h.hypothesis_id, h.title, h.status, h.created_at,
                  count(f.finding_id) AS findings,
                  max(f.created_at) AS last_finding
           FROM research.hypotheses h
           LEFT JOIN research.findings f ON f.hypothesis_id = h.hypothesis_id
           GROUP BY h.hypothesis_id, h.title, h.status, h.created_at
           ORDER BY last_finding DESC NULLS LAST""",
    ).fetchall()
    scored = [
        (h[0], h[1], h[2], h[3], h[4], h[5], _jaccard(probe, _tokens(h[1])))
        for h in rows
    ]
    scored = [s for s in scored if s[6] > 0]
    scored.sort(key=lambda s: s[6], reverse=True)
    return [
        {"hypothesis_id": s[0], "title": s[1], "status": s[2],
         "created_at": s[3], "findings": s[4], "last_finding": s[5],
         "similarity": round(s[6], 3)}
        for s in scored[:limit]
    ]


def search_findings(
    connection: Any, text: str | None = None, *,
    status: str | None = None, limit: int = 20
) -> list[dict[str, Any]]:
    """Findings filtered by verdict status and/or lexical match on conclusion."""
    rows = connection.execute(
        """SELECT f.finding_id, h.title AS hypothesis, f.status,
                  f.conclusion, f.evidence, f.created_at
           FROM research.findings f
           JOIN research.hypotheses h ON h.hypothesis_id = f.hypothesis_id
           WHERE (%s::text IS NULL OR f.status = %s::text)
           ORDER BY f.created_at DESC LIMIT 500""",
        (status, status),
    ).fetchall()
    probe = _tokens(text) if text else None
    out = []
    for r in rows:
        sim = _jaccard(probe, _tokens(r[3])) if probe else 1.0
        if probe and sim == 0:
            continue
        out.append({"finding_id": r[0], "hypothesis": r[1], "status": r[2],
                    "conclusion": r[3], "evidence": r[4], "created_at": r[5],
                    "similarity": round(sim, 3) if probe else None})
    out.sort(key=lambda x: (x["similarity"] or 0), reverse=True)
    return out[:limit]


def search_experiments(
    connection: Any, text: str, *, limit: int = 20
) -> list[dict[str, Any]]:
    """Experiments ranked by lexical overlap of hypothesis + config."""
    probe = _tokens(text)
    rows = connection.execute(
        """SELECT e.experiment_id, h.title, mv.code, e.code_version,
                  e.configuration::text, e.created_at,
                  count(DISTINCT er.experiment_run_id) AS runs
           FROM research.experiments e
           JOIN research.hypotheses h ON h.hypothesis_id = e.hypothesis_id
           LEFT JOIN research.model_versions mv
             ON mv.model_version_id = e.model_version_id
           LEFT JOIN research.experiment_runs er
             ON er.experiment_id = e.experiment_id
           GROUP BY e.experiment_id, h.title, mv.code, e.code_version,
                    e.configuration, e.created_at""",
    ).fetchall()
    scored = []
    for r in rows:
        hay = f"{r[1]} {r[2]} {r[3]} {r[4]}"
        sim = _jaccard(probe, _tokens(hay))
        if sim > 0:
            scored.append({"experiment_id": r[0], "hypothesis": r[1],
                           "model_code": r[2], "code_version": r[3],
                           "configuration": r[4], "created_at": r[5],
                           "runs": r[6], "similarity": round(sim, 3)})
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:limit]


def find_similar_experiments(
    connection: Any, experiment_id: UUID, *, limit: int = 10
) -> list[dict[str, Any]]:
    """Experiments structurally similar to `experiment_id`: same hypothesis,
    or model code overlap in configs."""
    src = connection.execute(
        """SELECT e.hypothesis_id, e.configuration::text
           FROM research.experiments e WHERE e.experiment_id = %s""",
        (experiment_id,),
    ).fetchone()
    if src is None:
        return []
    hypothesis_id, config_text = src
    probe = _tokens(config_text)
    rows = connection.execute(
        """SELECT e.experiment_id, mv.code, e.configuration::text,
                  (e.hypothesis_id = %s) AS same_hypothesis
           FROM research.experiments e
           LEFT JOIN research.model_versions mv
             ON mv.model_version_id = e.model_version_id
           WHERE e.experiment_id <> %s""",
        (hypothesis_id, experiment_id),
    ).fetchall()
    scored = []
    for r in rows:
        sim = _jaccard(probe, _tokens(r[2]))
        rank = sim + (0.5 if r[3] else 0.0)
        if sim > 0 or r[3]:
            scored.append({"experiment_id": r[0], "model_code": r[1],
                           "same_hypothesis": r[3],
                           "similarity": round(sim, 3), "rank": round(rank, 3)})
    scored.sort(key=lambda x: x["rank"], reverse=True)
    return scored[:limit]


def get_model_history(connection: Any, model_code: str) -> dict[str, Any]:
    """Everything recorded about a model: versions, cohort membership,
    predictions, settled outcomes, findings mentioning it."""
    versions = connection.execute(
        """SELECT model_version_id, version, definition, created_at
           FROM research.model_versions WHERE code = %s ORDER BY version""",
        (model_code,),
    ).fetchall()
    pred = connection.execute(
        """SELECT p.status, count(*) FROM research.predictions p
           JOIN research.model_versions mv ON mv.model_version_id = p.model_version_id
           WHERE mv.code = %s GROUP BY p.status""",
        (model_code,),
    ).fetchall()
    outcomes = connection.execute(
        """SELECT count(*), avg(o.hit_count)::numeric(10,4),
                  sum((o.metrics->'turbo'->'turbo_2'->>'net')::numeric)
           FROM research.prediction_outcomes o
           JOIN research.predictions p ON p.prediction_id = o.prediction_id
           JOIN research.model_versions mv ON mv.model_version_id = p.model_version_id
           WHERE mv.code = %s""",
        (model_code,),
    ).fetchone()
    findings = [
        dict(r) for r in search_findings(connection, model_code, limit=10)
    ]
    return {
        "model_code": model_code,
        "versions": [{"model_version_id": v[0], "version": v[1],
                      "definition": v[2], "created_at": v[3]} for v in versions],
        "predictions_by_status": {r[0]: r[1] for r in pred},
        "settled": {"count": outcomes[0], "mean_hits": outcomes[1],
                    "turbo2_net": outcomes[2]},
        "findings": findings,
    }


def get_strategy_history(connection: Any, limit: int = 20) -> list[dict[str, Any]]:
    """Strategy versions with their realized settlements."""
    rows = connection.execute(
        """SELECT sv.strategy_version_id, s.code, sv.version,
                  sv.payout_rule_version_id,
                  count(ss.settlement_id) AS settlements,
                  sum(ss.net_profit)::numeric(12,2) AS total_net
           FROM research.strategy_versions sv
           JOIN research.strategies s ON s.strategy_id = sv.strategy_id
           LEFT JOIN research.strategy_settlements ss
             ON ss.strategy_version_id = sv.strategy_version_id
           GROUP BY 1, 2, 3, 4 ORDER BY s.code, sv.version""",
    ).fetchall()
    return [
        {"strategy_version_id": r[0], "code": r[1], "version": r[2],
         "payout_rule_version_id": r[3], "settlements": r[4],
         "total_net": r[5]}
        for r in rows
    ]


def get_failure_history(connection: Any, *, limit: int = 50) -> list[dict[str, Any]]:
    """Rejected/inconclusive knowledge first — the anti-repeat wall Hermes
    must consult before proposing an experiment."""
    return search_findings(connection, status="REJECTED", limit=limit) + [
        f for f in search_findings(connection, status="INCONCLUSIVE", limit=limit)
    ]
