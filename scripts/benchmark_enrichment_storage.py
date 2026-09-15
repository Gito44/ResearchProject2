"""Benchmark SemGEM's enrichment persistence path with synthetic assertions."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import time

from semgem.core.records import (
    EnrichmentAssertionRecord,
    EntityAssertionEvidenceRecord,
    ExternalTermRecord,
)
from semgem.database.sqlite import SemanticDatabase


def assertions(entity_ids: list[int], provider: str, run_id: int):
    return tuple(
        EnrichmentAssertionRecord(
            entity_id=entity_id,
            predicate="maps_to_test_term",
            term_source="benchmark",
            term_identifier="TERM:1",
            evidence=(
                EntityAssertionEvidenceRecord(
                    provider=provider,
                    evidence_type="benchmark",
                    retrieval_method="synthetic",
                    run_id=run_id,
                ),
            ),
        )
        for entity_id in entity_ids
    )


def run(count: int) -> None:
    schema = Path(__file__).parents[1] / "semgem" / "database" / "schema.sql"
    with tempfile.TemporaryDirectory(prefix="semgem-storage-benchmark-") as tmp:
        database_path = Path(tmp) / "benchmark.sqlite"
        with SemanticDatabase(database_path, schema) as database:
            database.initialise()
            with database.conn:
                model_id = database.conn.execute(
                    """
                    INSERT INTO models (
                        original_id, name, source_file, content_hash,
                        compartments_json
                    ) VALUES ('benchmark', 'Benchmark', 'synthetic', 'synthetic', '{}')
                    """
                ).lastrowid
                database.conn.executemany(
                    """
                    INSERT INTO entities (model_id, entity_type, original_id, name)
                    VALUES (?, 'reaction', ?, NULL)
                    """,
                    ((model_id, f"R{index}") for index in range(count)),
                )
            entity_ids = [
                row[0]
                for row in database.conn.execute(
                    "SELECT id FROM entities ORDER BY id"
                )
            ]
            term = ExternalTermRecord(
                source="benchmark",
                identifier="TERM:1",
                term_type="reaction",
            )

            timings = []
            for provider in ("first", "second"):
                run_id = database.start_enrichment_run(
                    provider,
                    datetime.now(timezone.utc).isoformat(),
                )
                started = time.perf_counter()
                database.store_enrichment(
                    [term],
                    [],
                    assertions(entity_ids, provider, run_id),
                )
                timings.append((provider, time.perf_counter() - started))

            evidence_count = database.conn.execute(
                "SELECT COUNT(*) FROM entity_assertion_evidence"
            ).fetchone()[0]

    print(f"entities={count} evidence_rows={evidence_count}")
    for provider, seconds in timings:
        print(f"{provider}_provider_seconds={seconds:.6f}")
    print(f"total_seconds={sum(seconds for _, seconds in timings):.6f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=5_000)
    args = parser.parse_args()
    run(args.count)


if __name__ == "__main__":
    main()
