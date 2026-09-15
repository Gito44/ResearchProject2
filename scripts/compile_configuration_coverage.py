"""Compile reaction assignment coverage across SemGEM provider catalogs."""

from __future__ import annotations

import argparse
import csv
import sqlite3
from collections import defaultdict
from pathlib import Path
from statistics import mean, median


QUALITY_SUFFIXES = (
    "no_xrefs_no_subsystems",
    "no_metabolite_xrefs",
    "no_reaction_xrefs",
    "no_subsystems",
    "no_xrefs",
)


def model_design(source_file: str) -> tuple[str, str]:
    name = Path(source_file).name
    for extension in (".xml.gz", ".sbml.gz", ".xml", ".sbml"):
        if name.lower().endswith(extension):
            name = name[: -len(extension)]
            break
    for quality in QUALITY_SUFFIXES:
        suffix = f"__{quality}"
        if name.endswith(suffix):
            return name[: -len(suffix)], quality
    return name, "original"


def catalog_rows(path: Path) -> list[dict[str, object]]:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        unfinished = connection.execute(
            "SELECT provider, status FROM enrichment_runs "
            "WHERE status IN ('running', 'failed')"
        ).fetchall()
        if unfinished:
            raise ValueError(f"Catalog has unfinished or failed providers: {path}")
        providers = "+".join(
            row[0]
            for row in connection.execute(
                "SELECT provider FROM enrichment_runs ORDER BY id"
            )
        )
        rows = connection.execute(
            """
            WITH reaction_flags AS (
                SELECT model.original_id AS model_id,
                       model.source_file,
                       entity.id AS entity_id,
                       COUNT(concept.id) AS assignment_count,
                       MAX(CASE WHEN concept.concept_name LIKE 'pathway:%'
                                THEN 1 ELSE 0 END) AS pathway,
                       MAX(CASE
                           WHEN concept.concept_name LIKE 'pathway:%'
                             OR concept.concept_name LIKE 'objective:%'
                             OR concept.concept_name LIKE 'exchange:%'
                             OR concept.concept_name LIKE 'transport:%'
                             OR (
                                 concept.concept_name LIKE 'reaction_type:%'
                                 AND concept.concept_name <>
                                     'reaction_type:biochemical_reaction'
                             )
                           THEN 1 ELSE 0 END) AS actionable,
                       MAX(CASE WHEN concept.id IS NOT NULL
                                THEN 1 ELSE 0 END) AS assigned
                FROM entities AS entity
                JOIN models AS model ON model.id = entity.model_id
                LEFT JOIN semantic_concepts AS concept
                  ON concept.entity_id = entity.id
                WHERE entity.entity_type = 'reaction'
                GROUP BY entity.id
            )
            SELECT model_id,
                   source_file,
                   COUNT(*) AS total_reactions,
                   SUM(assignment_count) AS semantic_assignments,
                   SUM(assigned) AS assigned_reactions,
                   SUM(pathway) AS pathway_reactions,
                   SUM(actionable) AS actionable_reactions,
                   SUM(CASE WHEN assigned = 1 AND actionable = 0
                            THEN 1 ELSE 0 END) AS generic_only_reactions,
                   SUM(CASE WHEN assigned = 0 THEN 1 ELSE 0 END)
                       AS unclassified_reactions
            FROM reaction_flags
            GROUP BY model_id, source_file
            ORDER BY source_file
            """
        ).fetchall()
    finally:
        connection.close()

    output = []
    for row in rows:
        total = row["total_reactions"]
        base_model, quality = model_design(row["source_file"])
        output.append(
            {
                "configuration": path.stem,
                "providers": providers,
                "base_model": base_model,
                "quality_condition": quality,
                "model_id": row["model_id"],
                "source_file": row["source_file"],
                "total_reactions": total,
                "semantic_assignments": row["semantic_assignments"],
                "assigned_reactions": row["assigned_reactions"],
                "assignment_percent": 100 * row["assigned_reactions"] / total,
                "pathway_reactions": row["pathway_reactions"],
                "pathway_percent": 100 * row["pathway_reactions"] / total,
                "actionable_reactions": row["actionable_reactions"],
                "actionable_percent": 100 * row["actionable_reactions"] / total,
                "generic_only_reactions": row["generic_only_reactions"],
                "generic_only_percent": (
                    100 * row["generic_only_reactions"] / total
                ),
                "unclassified_reactions": row["unclassified_reactions"],
                "unclassified_percent": (
                    100 * row["unclassified_reactions"] / total
                ),
            }
        )
    return output


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog_directory", type=Path)
    parser.add_argument("--out-dir", type=Path)
    arguments = parser.parse_args()
    catalogs = sorted(arguments.catalog_directory.glob("*.sqlite"))
    if not catalogs:
        raise SystemExit("No SQLite catalogs found.")

    output_directory = arguments.out_dir or arguments.catalog_directory
    output_directory.mkdir(parents=True, exist_ok=True)
    rows = [row for catalog in catalogs for row in catalog_rows(catalog)]
    write_rows(output_directory / "assignment_coverage_long.csv", rows)

    configurations = [catalog.stem for catalog in catalogs]
    by_model: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in rows:
        key = (
            str(row["base_model"]),
            str(row["quality_condition"]),
            str(row["model_id"]),
        )
        output = by_model.setdefault(
            key,
            {
                "base_model": key[0],
                "quality_condition": key[1],
                "model_id": key[2],
                "total_reactions": row["total_reactions"],
            },
        )
        output[str(row["configuration"])] = row["assignment_percent"]
    wide_rows = list(by_model.values())
    wide_path = output_directory / "assignment_percent_wide.csv"
    with wide_path.open("w", encoding="utf-8", newline="") as file:
        fields = [
            "base_model",
            "quality_condition",
            "model_id",
            "total_reactions",
            *configurations,
        ]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(wide_rows)

    paired_models = {
        str(row["base_model"])
        for row in rows
        if row["quality_condition"] != "original"
    }
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        key = (str(row["quality_condition"]), str(row["configuration"]))
        grouped[("all_available", *key)].append(row)
        if str(row["base_model"]) in paired_models:
            grouped[("paired_quality_models", *key)].append(row)
    summary_rows = []
    for (cohort, quality, configuration), observations in sorted(grouped.items()):
        values = [float(row["assignment_percent"]) for row in observations]
        total = sum(int(row["total_reactions"]) for row in observations)
        summary_rows.append({
            "comparison_cohort": cohort,
            "quality_condition": quality,
            "configuration": configuration,
            "model_count": len(values),
            "total_reactions": total,
            "mean_assignment_percent": mean(values),
            "median_assignment_percent": median(values),
            "minimum_assignment_percent": min(values),
            "maximum_assignment_percent": max(values),
            "pooled_assignment_percent": (
                100 * sum(int(row["assigned_reactions"]) for row in observations)
                / total
            ),
            "mean_actionable_percent": mean(
                float(row["actionable_percent"]) for row in observations
            ),
            "mean_pathway_percent": mean(
                float(row["pathway_percent"]) for row in observations
            ),
        })
    write_rows(
        output_directory / "assignment_coverage_quality_summary.csv",
        summary_rows,
    )


if __name__ == "__main__":
    main()
