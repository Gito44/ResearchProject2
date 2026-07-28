"""Evaluate static SemGEM inference against hidden SBML subsystem labels.

This is a development benchmark. Source subsystem labels are retained only as
ground truth and are removed from the in-memory model before SemGEM runs.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from semgem.database.sqlite import SemanticDatabase
from semgem.evidence.concepts import ConceptRegistry
from semgem.evidence.load_rules import load_concepts, load_evidence_policy
from semgem.enrichment import KeggProvider, MetaNetXProvider
from semgem.extract.extractor import Extractor
from semgem.io.load_model import calculate_file_hash, load_sbml_model
from semgem.pipeline import SemanticPipeline


EVALUATED_CATEGORIES = {"pathway", "reaction_type", "transport"}


def split_subsystems(value: str | None) -> tuple[str, ...]:
    """Return individual labels from a semicolon-delimited subsystem value."""
    return tuple(
        label.strip()
        for label in str(value or "").split(";")
        if label.strip()
    )


def classification_metrics(predictions: set, ground_truth: set) -> dict:
    true_positive = len(predictions & ground_truth)
    false_positive = len(predictions - ground_truth)
    false_negative = len(ground_truth - predictions)
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
        "ground_truth_pairs": len(ground_truth),
        "predicted_pairs": len(predictions),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def benchmark(
    model_path: Path,
    metanetx_xref: Path | None = None,
    use_kegg: bool = False,
) -> dict:
    resources = Path(__file__).parents[1] / "semgem" / "resources"
    schema_path = Path(__file__).parents[1] / "semgem" / "database" / "schema.sql"
    concepts = load_concepts(resources / "concepts.toml")
    policy = load_evidence_policy(resources / "evidence_rules.toml", concepts)
    registry = ConceptRegistry(concepts)

    model = load_sbml_model(model_path)
    ground_truth_labels = {
        reaction.id: split_subsystems(reaction.subsystem)
        for reaction in model.reactions
    }
    ground_truth = {
        (reaction_id, concept_id)
        for reaction_id, labels in ground_truth_labels.items()
        for label in labels
        for concept_id in registry.match_label(label)
        if concepts[concept_id].category in EVALUATED_CATEGORIES
    }
    source_labels = {
        label
        for labels in ground_truth_labels.values()
        for label in labels
    }
    supported_labels = {
        label for label in source_labels if registry.match_label(label)
    }

    # Prevent both direct subsystem matching and accidental combined-text leakage.
    for reaction in model.reactions:
        reaction.subsystem = ""
    if not str(model.id or "").strip():
        model.id = "iRC1080_Chapman3_benchmark"

    extractor = Extractor(model)
    with tempfile.TemporaryDirectory(prefix="semgem-benchmark-") as directory:
        database_path = Path(directory) / "benchmark.sqlite"
        with SemanticDatabase(database_path, schema_path) as database:
            database.initialise()
            database.import_model(
                model=model,
                source_file=str(model_path),
                content_hash=calculate_file_hash(model_path),
                reactions=extractor.extract_reactions(),
                metabolites=extractor.extract_metabolites(),
                genes=extractor.extract_genes(),
                stoichiometry=extractor.extract_stoichiometry(),
                reaction_genes=extractor.extract_reaction_genes(),
            )
            providers = []
            if metanetx_xref is not None:
                providers.append(MetaNetXProvider(metanetx_xref))
            if use_kegg:
                providers.append(KeggProvider())
            summary = SemanticPipeline(registry, policy).run(
                database,
                providers=providers,
                include_subsystem_evidence=False,
            )
            predictions = {
                (row[0], row[1])
                for row in database.conn.execute(
                    """
                    SELECT entity.original_id, concept.concept_name
                    FROM semantic_concepts AS concept
                    JOIN entities AS entity ON entity.id = concept.entity_id
                    """
                ).fetchall()
                if (
                    row[1] in concepts
                    and concepts[row[1]].category in EVALUATED_CATEGORIES
                )
            }

    benchmark_concepts = {concept_id for _, concept_id in ground_truth}
    comparable_predictions = {
        pair for pair in predictions if pair[1] in benchmark_concepts
    }
    category_metrics = {}
    for category in sorted(EVALUATED_CATEGORIES):
        category_concepts = {
            concept_id
            for concept_id, concept in concepts.items()
            if concept.category == category
        }
        category_metrics[category] = classification_metrics(
            {pair for pair in comparable_predictions if pair[1] in category_concepts},
            {pair for pair in ground_truth if pair[1] in category_concepts},
        )
    predicted_reactions = {reaction_id for reaction_id, _ in predictions}
    supported_reactions = {reaction_id for reaction_id, _ in ground_truth}

    result = {
        "model": model.id,
        "reactions": len(model.reactions),
        "source_subsystem_labels": len(source_labels),
        "supported_subsystem_labels": len(supported_labels),
        "supported_ground_truth_reactions": len(supported_reactions),
        "predicted_reactions": len(predicted_reactions),
        "reaction_coverage": len(predicted_reactions) / len(model.reactions),
        "all_static_prediction_pairs": len(predictions),
        "comparable_metrics": classification_metrics(
            comparable_predictions,
            ground_truth,
        ),
        "metrics_by_category": category_metrics,
        "candidate_evidence": summary.candidate_count,
        "semantic_conclusions": summary.concept_count,
        "providers": [
            {
                "provider": provider.provider,
                "status": provider.status,
                "requested": provider.requested,
                "resolved": provider.resolved,
                "unresolved": provider.unresolved,
            }
            for provider in summary.providers
        ],
        "unsupported_labels": sorted(source_labels - supported_labels),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", type=Path)
    parser.add_argument("--metanetx-xref", type=Path)
    parser.add_argument("--kegg", action="store_true")
    arguments = parser.parse_args()
    print(
        json.dumps(
            benchmark(
                arguments.model,
                metanetx_xref=arguments.metanetx_xref,
                use_kegg=arguments.kegg,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
