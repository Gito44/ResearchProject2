from evaluation.benchmark_subsystems import (
    classification_metrics,
    hierarchy_aware_reaction_metrics,
    reaction_coverage_metrics,
    split_subsystems,
)
from evaluation.evaluate_catalog_accuracy import semantic_coverage
from semgem.evidence.concepts import ConceptRegistry
from semgem.evidence.rules import ConceptDefinition


def test_composite_subsystem_labels_are_split():
    assert split_subsystems(
        "Glycolysis / Gluconeogenesis;Carbon fixation"
    ) == (
        "Glycolysis / Gluconeogenesis",
        "Carbon fixation",
    )


def test_classification_metrics_support_multilabel_pairs():
    expected = {
        ("R1", "pathway:glycolysis_gluconeogenesis"),
        ("R1", "pathway:carbon_fixation"),
        ("R2", "pathway:glycolysis_gluconeogenesis"),
    }
    predicted = {
        ("R1", "pathway:glycolysis_gluconeogenesis"),
        ("R2", "pathway:glycolysis_gluconeogenesis"),
        ("R3", "pathway:glycolysis_gluconeogenesis"),
    }

    metrics = classification_metrics(predicted, expected)

    assert metrics["true_positive"] == 2
    assert metrics["false_positive"] == 1
    assert metrics["false_negative"] == 1
    assert metrics["precision"] == 2 / 3
    assert metrics["recall"] == 2 / 3


def test_reaction_coverage_separates_model_coverage_from_reference_recall():
    expected = {
        ("R1", "pathway:glycolysis_gluconeogenesis"),
        ("R2", "pathway:tca"),
    }
    predicted = {
        ("R1", "pathway:glycolysis_gluconeogenesis"),
        ("R3", "pathway:glycolysis_gluconeogenesis"),
    }

    metrics = reaction_coverage_metrics(predicted, expected, total_reactions=4)

    assert metrics["predicted_reactions"] == 2
    assert metrics["whole_model_coverage"] == 0.5
    assert metrics["reference_reactions"] == 2
    assert metrics["correctly_recovered_reference_reactions"] == 1
    assert metrics["reference_reaction_recall"] == 0.5


def test_hierarchy_metrics_separate_narrow_recovery_from_broad_only_help():
    concepts = {
        "pathway:metabolism": ConceptDefinition(
            "pathway:metabolism", "pathway", "Metabolism"
        ),
        "pathway:carbohydrate": ConceptDefinition(
            "pathway:carbohydrate",
            "pathway",
            "Carbohydrate metabolism",
            parents=("pathway:metabolism",),
        ),
        "pathway:glycolysis_gluconeogenesis": ConceptDefinition(
            "pathway:glycolysis_gluconeogenesis",
            "pathway",
            "Glycolysis",
            parents=("pathway:carbohydrate",),
        ),
    }
    registry = ConceptRegistry(concepts)
    expected = {
        ("R1", "pathway:glycolysis_gluconeogenesis"),
        ("R2", "pathway:glycolysis_gluconeogenesis"),
        ("R3", "pathway:carbohydrate"),
    }
    predicted = {
        ("R1", "pathway:glycolysis_gluconeogenesis"),
        ("R2", "pathway:carbohydrate"),
        ("R3", "pathway:glycolysis_gluconeogenesis"),
    }

    metrics = hierarchy_aware_reaction_metrics(predicted, expected, registry)

    assert metrics["exact_recovered_reactions"] == 1
    assert metrics["specificity_preserving_recovered_reactions"] == 2
    assert metrics["broad_only_recovered_reactions"] == 1
    assert metrics["hierarchy_compatible_recall"] == 1.0


def test_semantic_coverage_separates_actionable_from_generic_assignments():
    concepts = {
        "pathway:glycolysis_gluconeogenesis": ConceptDefinition(
            "pathway:glycolysis_gluconeogenesis", "pathway", "Glycolysis"
        ),
        "reaction_type:exchange_reaction": ConceptDefinition(
            "reaction_type:exchange_reaction", "reaction_type", "Exchange"
        ),
        "reaction_type:biochemical_reaction": ConceptDefinition(
            "reaction_type:biochemical_reaction",
            "reaction_type",
            "Biochemical reaction",
        ),
    }
    predictions = {
        ("R1", "pathway:glycolysis_gluconeogenesis"),
        ("R2", "reaction_type:exchange_reaction"),
        ("R3", "reaction_type:biochemical_reaction"),
    }

    result = semantic_coverage(predictions, total=4, concepts=concepts)

    assert result["pathway_reactions"] == 1
    assert result["actionable_non_pathway_reactions"] == 1
    assert result["actionable_reactions"] == 2
    assert result["generic_only_reactions"] == 1
    assert result["unclassified_reactions"] == 1
