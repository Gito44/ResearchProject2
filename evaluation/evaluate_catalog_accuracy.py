"""Evaluate a populated SemGEM catalog against hidden subsystem labels.

External enrichment assertions are reused from the catalog, while subsystem
evidence is suppressed during rescoring. The source SBML subsystem labels are
therefore used only as a reference and cannot leak into the predictions.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from evaluation.benchmark_subsystems import (
    classification_metrics,
    hierarchy_aware_reaction_metrics,
    reaction_coverage_metrics,
    split_subsystems,
)
from semgem.database.sqlite import SemanticDatabase
from semgem.evidence.concepts import ConceptRegistry
from semgem.evidence.engine import (
    EvidenceScorer,
    ExternalEvidenceGenerator,
    ModelEvidenceGenerator,
)
from semgem.evidence.load_rules import load_concepts, load_evidence_policy
from semgem.io.load_model import load_sbml_model


REFERENCE_CATEGORIES = {
    "pathway",
    "reaction_type",
    "transport",
    "objective",
    "exchange",
}
LEGACY_CATEGORIES = {"pathway", "reaction_type", "transport"}
GENERIC_CONCEPTS = {"reaction_type:biochemical_reaction"}


def is_actionable_concept(concept_id: str, concepts) -> bool:
    """Return whether a conclusion is useful for model navigation or analysis."""
    concept = concepts[concept_id]
    return (
        concept.category in {"pathway", "objective", "exchange", "transport"}
        or (
            concept.category == "reaction_type"
            and concept_id not in GENERIC_CONCEPTS
        )
    )


def semantic_coverage(predictions: set[tuple[str, str]], total: int, concepts) -> dict:
    """Partition reactions into pathway, actionable non-pathway, generic or none."""
    pathway = {
        reaction_id
        for reaction_id, concept_id in predictions
        if concepts[concept_id].category == "pathway"
    }
    actionable = {
        reaction_id
        for reaction_id, concept_id in predictions
        if is_actionable_concept(concept_id, concepts)
    }
    covered = {reaction_id for reaction_id, _ in predictions}
    actionable_non_pathway = actionable - pathway
    generic_only = covered - actionable
    unclassified = max(total - len(covered), 0)

    def proportion(count: int) -> float:
        return count / total if total else 0.0

    return {
        "total_reactions": total,
        "pathway_reactions": len(pathway),
        "pathway_coverage": proportion(len(pathway)),
        "actionable_non_pathway_reactions": len(actionable_non_pathway),
        "actionable_non_pathway_coverage": proportion(
            len(actionable_non_pathway)
        ),
        "actionable_reactions": len(actionable),
        "actionable_coverage": proportion(len(actionable)),
        "generic_only_reactions": len(generic_only),
        "generic_only_coverage": proportion(len(generic_only)),
        "unclassified_reactions": unclassified,
        "unclassified_coverage": proportion(unclassified),
    }


def evaluate(database_path: Path, project_root: Path) -> dict:
    resources = project_root / "semgem" / "resources"
    schema = project_root / "semgem" / "database" / "schema.sql"
    concepts = load_concepts(resources / "concepts.toml")
    policy = load_evidence_policy(resources / "evidence_rules.toml", concepts)
    registry = ConceptRegistry(concepts)

    with SemanticDatabase(database_path, schema) as database:
        database.initialise()
        model_rows = database.conn.execute(
            "SELECT id, original_id, source_file FROM models ORDER BY id"
        ).fetchall()
        entity_identity = {
            row[0]: (row[1], row[2])
            for row in database.conn.execute(
                """
                SELECT id, model_id, original_id
                FROM entities
                WHERE entity_type = 'reaction'
                """
            )
        }
        candidates = [
            *ModelEvidenceGenerator(policy, registry).generate(
                database,
                include_subsystem_evidence=False,
            ),
            *ExternalEvidenceGenerator(registry, policy).generate(database),
        ]
        conclusions = EvidenceScorer(policy, concepts).score(candidates)

    predictions_by_model: dict[int, set[tuple[str, str]]] = defaultdict(set)
    for conclusion in conclusions:
        identity = entity_identity.get(conclusion.entity_id)
        if identity is None:
            continue
        model_database_id, reaction_id = identity
        if concepts[conclusion.concept_id].category in REFERENCE_CATEGORIES:
            predictions_by_model[model_database_id].add(
                (reaction_id, conclusion.concept_id)
            )

    pathway_concepts = {
        concept_id
        for concept_id, concept in concepts.items()
        if concept.category == "pathway"
    }
    results = []
    legacy_aggregate_predictions = set()
    legacy_aggregate_ground_truth = set()
    aggregate_predictions = set()
    aggregate_ground_truth = set()
    aggregate_coverage_predictions = set()
    aggregate_reactions = 0
    for model_database_id, model_id, source_file in model_rows:
        source_path = Path(source_file)
        if not source_path.exists():
            continue
        model = load_sbml_model(source_path)
        ground_truth = {
            (reaction.id, concept_id)
            for reaction in model.reactions
            for label in split_subsystems(reaction.subsystem)
            for concept_id in registry.match_label(label)
            if concepts[concept_id].category in REFERENCE_CATEGORIES
        }
        if not ground_truth:
            continue
        predictions = predictions_by_model.get(model_database_id, set())
        reaction_names = {
            reaction.id: reaction.name or reaction.id for reaction in model.reactions
        }
        benchmark_concepts = {concept_id for _, concept_id in ground_truth}
        legacy_ground_truth = {
            pair
            for pair in ground_truth
            if concepts[pair[1]].category in LEGACY_CATEGORIES
        }
        legacy_benchmark_concepts = {
            concept_id for _, concept_id in legacy_ground_truth
        }
        comparable_predictions = {
            pair for pair in predictions if pair[1] in benchmark_concepts
        }
        legacy_comparable_predictions = {
            pair
            for pair in predictions
            if pair[1] in legacy_benchmark_concepts
            and concepts[pair[1]].category in LEGACY_CATEGORIES
        }
        evaluated_predictions = {
            pair
            for pair in predictions
            if concepts[pair[1]].category in REFERENCE_CATEGORIES
        }
        pathway_ground_truth = {
            pair for pair in ground_truth if pair[1] in pathway_concepts
        }
        pathway_predictions = {
            pair for pair in predictions if pair[1] in pathway_concepts
        }
        comparable_pathway_predictions = {
            pair for pair in comparable_predictions if pair[1] in pathway_concepts
        }
        scoped_legacy_predictions = {
            (f"{model_database_id}:{reaction_id}", concept_id)
            for reaction_id, concept_id in legacy_comparable_predictions
        }
        scoped_predictions = {
            (f"{model_database_id}:{reaction_id}", concept_id)
            for reaction_id, concept_id in evaluated_predictions
        }
        scoped_truth = {
            (f"{model_database_id}:{reaction_id}", concept_id)
            for reaction_id, concept_id in ground_truth
        }
        legacy_aggregate_predictions.update(scoped_legacy_predictions)
        legacy_aggregate_ground_truth.update(
            {
                (f"{model_database_id}:{reaction_id}", concept_id)
                for reaction_id, concept_id in legacy_ground_truth
            }
        )
        aggregate_predictions.update(scoped_predictions)
        aggregate_ground_truth.update(scoped_truth)
        aggregate_coverage_predictions.update(
            {
                (f"{model_database_id}:{reaction_id}", concept_id)
                for reaction_id, concept_id in predictions
            }
        )
        aggregate_reactions += len(model.reactions)
        true_positive_pairs = sorted(comparable_predictions & ground_truth)
        false_positive_pairs = sorted(comparable_predictions - ground_truth)
        false_negative_pairs = sorted(ground_truth - comparable_predictions)

        def examples(pairs: list[tuple[str, str]]) -> list[dict[str, str]]:
            return [
                {
                    "reaction_id": reaction_id,
                    "reaction_name": reaction_names.get(reaction_id, reaction_id),
                    "concept_id": concept_id,
                    "concept_label": concepts[concept_id].preferred_label,
                }
                for reaction_id, concept_id in pairs[:5]
            ]

        results.append(
            {
                "model_id": model_id,
                "reactions": len(model.reactions),
                "reference_pairs": len(ground_truth),
                "subsystem_labeled_reactions": sum(
                    bool(split_subsystems(reaction.subsystem))
                    for reaction in model.reactions
                ),
                "reference_reactions": len(
                    {reaction_id for reaction_id, _ in ground_truth}
                ),
                "legacy_comparable_metrics": classification_metrics(
                    legacy_comparable_predictions,
                    legacy_ground_truth,
                ),
                "unrestricted_reference_agreement": classification_metrics(
                    evaluated_predictions,
                    ground_truth,
                ),
                "semantic_coverage": semantic_coverage(
                    predictions,
                    len(model.reactions),
                    concepts,
                ),
                "metrics_by_category": {
                    category: classification_metrics(
                        {
                            pair
                            for pair in evaluated_predictions
                            if concepts[pair[1]].category == category
                        },
                        {
                            pair
                            for pair in ground_truth
                            if concepts[pair[1]].category == category
                        },
                    )
                    for category in sorted(REFERENCE_CATEGORIES)
                },
                "pathway_metrics": {
                    **classification_metrics(
                        comparable_pathway_predictions,
                        pathway_ground_truth,
                    ),
                    **reaction_coverage_metrics(
                        pathway_predictions,
                        pathway_ground_truth,
                        len(model.reactions),
                    ),
                    "hierarchy": hierarchy_aware_reaction_metrics(
                        pathway_predictions,
                        pathway_ground_truth,
                        registry,
                    ),
                },
                "examples": {
                    "true_positive": examples(true_positive_pairs),
                    "false_positive": examples(false_positive_pairs),
                    "false_negative": examples(false_negative_pairs),
                },
            }
        )

    return {
        "method": (
            "Provider-enriched predictions with source subsystem evidence "
            "suppressed; source subsystem labels used only as reference."
        ),
        "warnings": [
            "Subsystem labels are an incomplete proxy reference, not a gold standard.",
            "Unrestricted precision is observed agreement with that incomplete reference, not biological precision.",
            "Legacy comparable precision excludes predicted concepts absent from a model's supported reference vocabulary.",
            "Several reference models influenced rule development and are not independent held-out tests.",
        ],
        "models": results,
        "legacy_micro_comparable_metrics": classification_metrics(
            legacy_aggregate_predictions,
            legacy_aggregate_ground_truth,
        ),
        "micro_unrestricted_reference_agreement": classification_metrics(
            aggregate_predictions,
            aggregate_ground_truth,
        ),
        "micro_semantic_coverage": semantic_coverage(
            aggregate_coverage_predictions,
            aggregate_reactions,
            concepts,
        ),
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
    result = evaluate(arguments.database, arguments.project_root)
    text = json.dumps(result, indent=2)
    if arguments.out:
        arguments.out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
