"""Generate reproducible per-model SemGEM coverage and source ablations."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

from semgem.database.sqlite import SemanticDatabase
from semgem.evidence.concepts import ConceptRegistry
from semgem.evidence.engine import (
    EvidenceScorer,
    ExternalEvidenceGenerator,
    ModelEvidenceGenerator,
)
from semgem.evidence.load_rules import load_concepts, load_evidence_policy


def wilson_interval(successes: int, total: int, z: float = 1.96) -> list[float]:
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


def summarize_conclusions(conclusions, entity_to_model, concepts, reaction_counts):
    by_model = defaultdict(list)
    for conclusion in conclusions:
        model_id = entity_to_model.get(conclusion.entity_id)
        if model_id is not None:
            by_model[model_id].append(conclusion)

    output = {}
    for model_id, total in reaction_counts.items():
        values = by_model.get(model_id, [])
        covered = {item.entity_id for item in values}
        pathway_values = [
            item
            for item in values
            if concepts[item.concept_id].category == "pathway"
        ]
        pathway_covered = {item.entity_id for item in pathway_values}
        confidences = [item.confidence for item in values]
        output[model_id] = {
            "allocations": len(values),
            "covered_reactions": len(covered),
            "coverage": len(covered) / total if total else 0.0,
            "coverage_95_ci": wilson_interval(len(covered), total),
            "pathway_allocations": len(pathway_values),
            "pathway_covered_reactions": len(pathway_covered),
            "pathway_coverage": (
                len(pathway_covered) / total if total else 0.0
            ),
            "pathway_coverage_95_ci": wilson_interval(
                len(pathway_covered),
                total,
            ),
            "mean_confidence": mean(confidences) if confidences else 0.0,
            "median_confidence": median(confidences) if confidences else 0.0,
            "allocations_per_covered_reaction": (
                len(values) / len(covered) if covered else 0.0
            ),
        }
    return output


def provider_key(candidate, assertion_providers):
    if candidate.source != "external":
        return candidate.source
    providers = assertion_providers.get(candidate.assertion_id, set())
    if "metanetx_chemistry" in providers:
        return "metanetx_chemistry"
    return "external"


def analyze(database_path: Path, project_root: Path) -> dict:
    resources = project_root / "semgem" / "resources"
    schema = project_root / "semgem" / "database" / "schema.sql"
    concepts = load_concepts(resources / "concepts.toml")
    policy = load_evidence_policy(resources / "evidence_rules.toml", concepts)
    registry = ConceptRegistry(concepts)

    with SemanticDatabase(database_path, schema) as database:
        database.initialise()
        connection = database.conn
        models = {
            row[0]: {
                "database_id": row[0],
                "model_id": row[1],
                "name": row[2],
            }
            for row in connection.execute(
                "SELECT id, original_id, name FROM models ORDER BY original_id"
            )
        }
        entity_to_model = {
            row[0]: row[1]
            for row in connection.execute(
                """
                SELECT id, model_id
                FROM entities
                WHERE entity_type = 'reaction'
                """
            )
        }
        reaction_counts = dict(
            connection.execute(
                """
                SELECT model_id, COUNT(*)
                FROM entities
                WHERE entity_type = 'reaction'
                GROUP BY model_id
                """
            )
        )
        assertion_providers = defaultdict(set)
        for assertion_id, provider in connection.execute(
            """
            SELECT assertion_id, provider
            FROM entity_assertion_evidence
            """
        ):
            assertion_providers[assertion_id].add(provider)

        model_generator = ModelEvidenceGenerator(policy, registry)
        model_candidates = model_generator.generate(
            database,
            include_subsystem_evidence=True,
        )
        portable_model_candidates = model_generator.generate(
            database,
            include_subsystem_evidence=False,
        )
        external_candidates = ExternalEvidenceGenerator(
            registry,
            policy,
        ).generate(database)
        all_candidates = [*model_candidates, *external_candidates]
        portable_candidates = [
            *portable_model_candidates,
            *external_candidates,
        ]

        scenarios = {
            "all_evidence": all_candidates,
            "without_sbo": [
                item
                for item in all_candidates
                if provider_key(item, assertion_providers) != "sbo"
            ],
            "without_subsystems": portable_candidates,
            "portable_without_sbo_or_subsystems": [
                item
                for item in portable_candidates
                if provider_key(item, assertion_providers) != "sbo"
            ],
            "model_only": [
                item
                for item in model_candidates
                if item.source == "model"
            ],
            "sbo_only": [
                item
                for item in all_candidates
                if provider_key(item, assertion_providers) == "sbo"
            ],
            "kegg_only": [
                item
                for item in all_candidates
                if provider_key(item, assertion_providers) == "kegg"
            ],
            "metanetx_only": [
                item
                for item in all_candidates
                if provider_key(item, assertion_providers) == "metanetx"
            ],
            "rhea_only": [
                item
                for item in all_candidates
                if provider_key(item, assertion_providers) == "rhea"
            ],
            "metanetx_chemistry_only": [
                item
                for item in all_candidates
                if provider_key(item, assertion_providers)
                == "metanetx_chemistry"
            ],
        }
        scorer = EvidenceScorer(policy, concepts)
        scored = {
            name: scorer.score(candidates)
            for name, candidates in scenarios.items()
        }
        scenario_summaries = {
            name: summarize_conclusions(
                conclusions,
                entity_to_model,
                concepts,
                reaction_counts,
            )
            for name, conclusions in scored.items()
        }

        for model_id, model in models.items():
            model["reactions"] = reaction_counts.get(model_id, 0)
            model["metabolites"] = connection.execute(
                """
                SELECT COUNT(*)
                FROM entities
                WHERE model_id = ? AND entity_type = 'metabolite'
                """,
                (model_id,),
            ).fetchone()[0]
            model["genes"] = connection.execute(
                """
                SELECT COUNT(*)
                FROM entities
                WHERE model_id = ? AND entity_type = 'gene'
                """,
                (model_id,),
            ).fetchone()[0]
            model["subsystem_reactions"] = connection.execute(
                """
                SELECT COUNT(*)
                FROM reactions AS reaction
                JOIN entities AS entity ON entity.id = reaction.entity_id
                WHERE entity.model_id = ? AND reaction.subsystem <> ''
                """,
                (model_id,),
            ).fetchone()[0]
            annotation_counts = {
                row[0]: row[1]
                for row in connection.execute(
                    """
                    SELECT annotation.source, COUNT(DISTINCT entity.id)
                    FROM annotations AS annotation
                    JOIN entities AS entity ON entity.id = annotation.entity_id
                    WHERE entity.model_id = ?
                      AND entity.entity_type = 'reaction'
                    GROUP BY annotation.source
                    """,
                    (model_id,),
                )
            }
            model["reaction_annotations"] = {
                "sbo": annotation_counts.get("sbo", 0),
                "kegg": annotation_counts.get("kegg.reaction", 0),
                "rhea": annotation_counts.get("rhea", 0),
                "metanetx": annotation_counts.get("metanetx.reaction", 0),
                "bigg": (
                    annotation_counts.get("bigg.reaction", 0)
                    + annotation_counts.get("biggr", 0)
                ),
            }
            assertion_counts = {
                row[0]: row[1]
                for row in connection.execute(
                    """
                    SELECT assertion.predicate, COUNT(DISTINCT entity.id)
                    FROM enrichment_assertions AS assertion
                    JOIN entities AS entity ON entity.id = assertion.entity_id
                    WHERE entity.model_id = ?
                    GROUP BY assertion.predicate
                    """,
                    (model_id,),
                )
            }
            model["standardized_metabolites"] = assertion_counts.get(
                "maps_to_mnxref_chemical",
                0,
            )
            model["chemistry_matched_reactions"] = assertion_counts.get(
                "matches_mnxref_reaction_signature",
                0,
            )
            model["metanetx_reaction_identities"] = assertion_counts.get(
                "maps_to_mnxref_reaction",
                0,
            )
            model["rhea_reaction_identities"] = assertion_counts.get(
                "maps_to_rhea_reaction",
                0,
            )
            model["kegg_reaction_identities"] = assertion_counts.get(
                "has_kegg_reaction",
                0,
            )
            model["scenarios"] = {
                name: summary[model_id]
                for name, summary in scenario_summaries.items()
            }

    ordered_models = sorted(models.values(), key=lambda item: item["model_id"])
    aggregate = {}
    total_reactions = sum(item["reactions"] for item in ordered_models)
    for scenario_name in scenarios:
        allocations = sum(
            item["scenarios"][scenario_name]["allocations"]
            for item in ordered_models
        )
        covered = sum(
            item["scenarios"][scenario_name]["covered_reactions"]
            for item in ordered_models
        )
        pathway_allocations = sum(
            item["scenarios"][scenario_name]["pathway_allocations"]
            for item in ordered_models
        )
        pathway_covered = sum(
            item["scenarios"][scenario_name]["pathway_covered_reactions"]
            for item in ordered_models
        )
        aggregate[scenario_name] = {
            "allocations": allocations,
            "covered_reactions": covered,
            "coverage": covered / total_reactions,
            "coverage_95_ci": wilson_interval(covered, total_reactions),
            "pathway_allocations": pathway_allocations,
            "pathway_covered_reactions": pathway_covered,
            "pathway_coverage": pathway_covered / total_reactions,
            "pathway_coverage_95_ci": wilson_interval(
                pathway_covered,
                total_reactions,
            ),
        }
    return {
        "catalog": str(database_path),
        "models": ordered_models,
        "aggregate": aggregate,
        "notes": {
            "coverage_unit": "distinct reaction entities",
            "allocation_unit": "accepted reaction-concept pairs",
            "accuracy_warning": (
                "Coverage is not accuracy. Precision, recall, and F1 require "
                "an independent reference annotation."
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).parents[1],
    )
    parser.add_argument("--out", type=Path)
    arguments = parser.parse_args()
    result = analyze(arguments.database, arguments.project_root)
    text = json.dumps(result, indent=2)
    if arguments.out:
        arguments.out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
