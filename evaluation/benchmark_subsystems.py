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
from semgem.enrichment import (
    KeggProvider,
    MetaNetXChemistryProvider,
    MetaNetXProvider,
    RheaProvider,
)
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


def reaction_coverage_metrics(
    predictions: set[tuple[str, str]],
    ground_truth: set[tuple[str, str]],
    total_reactions: int,
) -> dict:
    """Report whole-model coverage and reference-reaction recovery.

    Whole-model pathway coverage measures the amount of pathway information a
    downstream user receives. Reference-reaction recovery uses only reactions
    carrying a supported curated pathway label and therefore does not penalise
    legitimate non-pathway reactions such as exchanges and demands.
    """
    predicted_reactions = {reaction_id for reaction_id, _ in predictions}
    reference_reactions = {reaction_id for reaction_id, _ in ground_truth}
    correctly_recovered = {
        reaction_id for reaction_id, concept_id in predictions & ground_truth
    }
    return {
        "predicted_reactions": len(predicted_reactions),
        "whole_model_coverage": (
            len(predicted_reactions) / total_reactions if total_reactions else 0.0
        ),
        "reference_reactions": len(reference_reactions),
        "correctly_recovered_reference_reactions": len(correctly_recovered),
        "reference_reaction_recall": (
            len(correctly_recovered) / len(reference_reactions)
            if reference_reactions
            else 0.0
        ),
    }


def hierarchy_aware_reaction_metrics(
    predictions: set[tuple[str, str]],
    ground_truth: set[tuple[str, str]],
    registry: ConceptRegistry,
) -> dict:
    """Measure exact, specificity-preserving, and broad-only recovery.

    A narrower prediction is sufficient for a broader reference because the
    narrower conclusion implies its ancestors. A broader prediction is useful
    but is reported separately: it must not masquerade as recovery of the
    more specific curated pathway.
    """
    predicted_by_reaction: dict[str, set[str]] = {}
    expected_by_reaction: dict[str, set[str]] = {}
    for reaction_id, concept_id in predictions:
        predicted_by_reaction.setdefault(reaction_id, set()).add(concept_id)
    for reaction_id, concept_id in ground_truth:
        expected_by_reaction.setdefault(reaction_id, set()).add(concept_id)

    exact = set()
    specificity_preserving = set()
    broad_only = set()
    for reaction_id, expected_ids in expected_by_reaction.items():
        predicted_ids = predicted_by_reaction.get(reaction_id, set())
        if predicted_ids & expected_ids:
            exact.add(reaction_id)
        if any(
            expected_id == predicted_id
            or expected_id in registry.ancestors(predicted_id)
            for expected_id in expected_ids
            for predicted_id in predicted_ids
        ):
            specificity_preserving.add(reaction_id)
            continue
        if any(
            registry.hierarchy_compatible(expected_id, predicted_id)
            for expected_id in expected_ids
            for predicted_id in predicted_ids
        ):
            broad_only.add(reaction_id)

    reference_count = len(expected_by_reaction)
    compatible = specificity_preserving | broad_only
    return {
        "reference_reactions": reference_count,
        "exact_recovered_reactions": len(exact),
        "specificity_preserving_recovered_reactions": len(specificity_preserving),
        "broad_only_recovered_reactions": len(broad_only),
        "hierarchy_compatible_reactions": len(compatible),
        "specificity_preserving_recall": (
            len(specificity_preserving) / reference_count
            if reference_count
            else 0.0
        ),
        "hierarchy_compatible_recall": (
            len(compatible) / reference_count if reference_count else 0.0
        ),
    }
def benchmark(
    model_path: Path,
    metanetx_xref: Path | None = None,
    metanetx_chem_xref: Path | None = None,
    metanetx_reac_prop: Path | None = None,
    metanetx_chem_prop: Path | None = None,
    rhea_xref: Path | None = None,
    use_kegg: bool = False,
    catalog_path: Path | None = None,
    reuse_catalog: bool = False,
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
    temporary_directory = None
    if catalog_path is None:
        temporary_directory = tempfile.TemporaryDirectory(
            prefix="semgem-benchmark-"
        )
        database_path = Path(temporary_directory.name) / "benchmark.sqlite"
    else:
        database_path = catalog_path
    try:
        with SemanticDatabase(database_path, schema_path) as database:
            database.initialise()
            if not reuse_catalog:
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
            if not reuse_catalog and (
                metanetx_xref is not None
                and metanetx_chem_xref is not None
                and metanetx_reac_prop is not None
            ):
                providers.append(
                    MetaNetXChemistryProvider(
                        chem_xref_path=metanetx_chem_xref,
                        chem_prop_path=metanetx_chem_prop,
                        reac_prop_path=metanetx_reac_prop,
                        reac_xref_path=metanetx_xref,
                    )
                )
            if not reuse_catalog and metanetx_xref is not None:
                providers.append(MetaNetXProvider(metanetx_xref))
            if not reuse_catalog and rhea_xref is not None:
                providers.append(RheaProvider(rhea_xref))
            if not reuse_catalog and use_kegg:
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
            metabolite_standardizations = database.conn.execute(
                """
                SELECT COUNT(DISTINCT entity_id)
                FROM enrichment_assertions
                WHERE predicate = 'maps_to_mnxref_chemical'
                """
            ).fetchone()[0]
            chemistry_reaction_matches = database.conn.execute(
                """
                SELECT COUNT(DISTINCT entity_id)
                FROM enrichment_assertions
                WHERE predicate = 'matches_mnxref_reaction_signature'
                """
            ).fetchone()[0]
    finally:
        if temporary_directory is not None:
            temporary_directory.cleanup()

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
    pathway_concepts = {
        concept_id
        for concept_id, concept in concepts.items()
        if concept.category == "pathway"
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
    pathway_by_concept = {}
    for concept_id in sorted({item[1] for item in pathway_ground_truth}):
        pathway_by_concept[concept_id] = classification_metrics(
            {pair for pair in comparable_pathway_predictions if pair[1] == concept_id},
            {pair for pair in pathway_ground_truth if pair[1] == concept_id},
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
            "by_concept": pathway_by_concept,
        },
        "candidate_evidence": summary.candidate_count,
        "semantic_conclusions": summary.concept_count,
        "metabolites_standardized": metabolite_standardizations,
        "chemistry_matched_reactions": chemistry_reaction_matches,
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
    parser.add_argument("--metanetx-chem-xref", type=Path)
    parser.add_argument("--metanetx-reac-prop", type=Path)
    parser.add_argument("--metanetx-chem-prop", type=Path)
    parser.add_argument("--rhea-xref", type=Path)
    parser.add_argument("--kegg", action="store_true")
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--reuse-catalog", action="store_true")
    arguments = parser.parse_args()
    print(
        json.dumps(
            benchmark(
                arguments.model,
                metanetx_xref=arguments.metanetx_xref,
                metanetx_chem_xref=arguments.metanetx_chem_xref,
                metanetx_reac_prop=arguments.metanetx_reac_prop,
                metanetx_chem_prop=arguments.metanetx_chem_prop,
                rhea_xref=arguments.rhea_xref,
                use_kegg=arguments.kegg,
                catalog_path=arguments.catalog,
                reuse_catalog=arguments.reuse_catalog,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
