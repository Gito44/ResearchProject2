"""Evaluate a SemGEM catalog against the manually curated benchmark."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import tomllib
from pathlib import Path

from semgem.evidence.concepts import normalize_label
from semgem.evidence.load_rules import load_concepts


def wilson_interval(successes: int, total: int, z: float = 1.96):
    """Return a two-sided Wilson score interval for a binomial proportion."""
    if total == 0:
        return [0.0, 1.0]
    proportion = successes / total
    denominator = 1 + z**2 / total
    center = (proportion + z**2 / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total
            + z**2 / (4 * total**2)
        )
        / denominator
    )
    return [max(0.0, center - margin), min(1.0, center + margin)]


def metrics(expected: set[tuple], predicted: set[tuple]) -> dict[str, object]:
    true_positive = len(expected & predicted)
    false_positive = len(predicted - expected)
    false_negative = len(expected - predicted)
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 0.0
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "precision_95_ci": wilson_interval(
            true_positive,
            true_positive + false_positive,
        ),
        "recall": recall,
        "recall_95_ci": wilson_interval(
            true_positive,
            true_positive + false_negative,
        ),
        "f1": f1,
    }


def load_benchmark(path: Path):
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    scoped = set(data["scoped_concepts"])
    expected = set()
    benchmark_entities = set()
    for item in data["sets"]:
        for reaction_id in item["reactions"]:
            key = (item["model"], reaction_id)
            benchmark_entities.add(key)
            expected.add((*key, item["concept"]))
    return data, scoped, benchmark_entities, expected


def evaluate(
    database_path: Path,
    benchmark_path: Path,
    concepts_path: Path,
    excluded_sources: set[str] | None = None,
):
    _, scoped, benchmark_entities, expected = load_benchmark(benchmark_path)
    concepts = load_concepts(concepts_path)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row

    entity_rows = connection.execute(
        """
        SELECT m.original_id AS model,
               e.original_id AS reaction_id,
               r.subsystem
        FROM entities AS e
        JOIN models AS m ON m.id = e.model_id
        JOIN reactions AS r ON r.entity_id = e.id
        """
    ).fetchall()
    available = {(row["model"], row["reaction_id"]) for row in entity_rows}
    missing_entities = sorted(benchmark_entities - available)
    if missing_entities:
        raise ValueError(
            f"Catalog is missing {len(missing_entities)} benchmark reactions: "
            f"{missing_entities[:5]}"
        )

    excluded_sources = excluded_sources or set()
    predicted_rows = connection.execute(
        """
        SELECT m.original_id AS model,
               e.original_id AS reaction_id,
               sc.concept_name,
               GROUP_CONCAT(DISTINCT ce.source) AS evidence_sources
        FROM semantic_concepts AS sc
        JOIN entities AS e ON e.id = sc.entity_id
        JOIN models AS m ON m.id = e.model_id
        LEFT JOIN concept_evidence AS ce ON ce.concept_id = sc.id
        GROUP BY sc.id
        """
    )
    predicted = {
        (row["model"], row["reaction_id"], row["concept_name"])
        for row in predicted_rows
        if (row["model"], row["reaction_id"]) in benchmark_entities
        and row["concept_name"] in scoped
        and (
            set((row["evidence_sources"] or "").split(",")) - excluded_sources
        )
    }

    # Portable naive baseline: one exact preferred-label comparison against the
    # raw subsystem. It represents what an application can do without
    # model-specific aliases, encoded-label handling, or external providers.
    baseline = set()
    preferred = {
        concept_id: normalize_label(concepts[concept_id].preferred_label)
        for concept_id in scoped
    }
    for row in entity_rows:
        key = (row["model"], row["reaction_id"])
        if key not in benchmark_entities:
            continue
        raw_label = normalize_label(row["subsystem"] or "")
        for concept_id, preferred_label in preferred.items():
            if raw_label and raw_label == preferred_label:
                baseline.add((*key, concept_id))

    by_model = {}
    for model in sorted({key[0] for key in benchmark_entities}):
        expected_model = {item for item in expected if item[0] == model}
        predicted_model = {item for item in predicted if item[0] == model}
        baseline_model = {item for item in baseline if item[0] == model}
        by_model[model] = {
            "semgem": metrics(expected_model, predicted_model),
            "portable_baseline": metrics(expected_model, baseline_model),
        }

    by_concept = {}
    for concept_id in sorted(scoped):
        expected_concept = {item for item in expected if item[2] == concept_id}
        predicted_concept = {item for item in predicted if item[2] == concept_id}
        if expected_concept or predicted_concept:
            by_concept[concept_id] = metrics(
                expected_concept,
                predicted_concept,
            )

    false_positives = sorted(predicted - expected)
    false_negatives = sorted(expected - predicted)
    result = {
        "benchmark_entities": len(benchmark_entities),
        "expected_positive_pairs": len(expected),
        "semgem": metrics(expected, predicted),
        "portable_baseline": metrics(expected, baseline),
        "by_model": by_model,
        "by_concept": by_concept,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "excluded_sources": sorted(excluded_sources),
    }
    connection.close()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=Path(__file__).with_name("curated_benchmark.toml"),
    )
    parser.add_argument(
        "--concepts",
        type=Path,
        default=Path(__file__).parents[1] / "semgem/resources/concepts.toml",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--exclude-source",
        action="append",
        default=[],
        help=(
            "Ignore conclusions supported only by this evidence source. "
            "May be repeated."
        ),
    )
    arguments = parser.parse_args()

    result = evaluate(
        arguments.database,
        arguments.benchmark,
        arguments.concepts,
        set(arguments.exclude_source),
    )
    if arguments.json:
        print(json.dumps(result, indent=2))
        return

    print(f"Benchmark reactions: {result['benchmark_entities']}")
    print(f"Expected positive pairs: {result['expected_positive_pairs']}")
    for name in ("portable_baseline", "semgem"):
        values = result[name]
        print(
            f"{name}: precision={values['precision']:.3f} "
            f"recall={values['recall']:.3f} f1={values['f1']:.3f} "
            f"TP={values['true_positive']} FP={values['false_positive']} "
            f"FN={values['false_negative']}"
        )
    print(f"False positives: {result['false_positives']}")
    print(f"False negatives: {result['false_negatives']}")


if __name__ == "__main__":
    main()
