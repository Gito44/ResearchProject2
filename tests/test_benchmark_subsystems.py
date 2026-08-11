from evaluation.benchmark_subsystems import (
    classification_metrics,
    hierarchy_aware_reaction_metrics,
    reaction_coverage_metrics,
    split_subsystems,
)
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
        ("R1", "pathway:glycolysis"),
        ("R1", "pathway:carbon_fixation"),
        ("R2", "pathway:glycolysis"),
    }
    predicted = {
        ("R1", "pathway:glycolysis"),
        ("R2", "pathway:glycolysis"),
        ("R3", "pathway:glycolysis"),
    }

    metrics = classification_metrics(predicted, expected)

    assert metrics["true_positive"] == 2
    assert metrics["false_positive"] == 1
    assert metrics["false_negative"] == 1
    assert metrics["precision"] == 2 / 3
    assert metrics["recall"] == 2 / 3


def test_reaction_coverage_separates_model_coverage_from_reference_recall():
    expected = {
        ("R1", "pathway:glycolysis"),
        ("R2", "pathway:tca"),
    }
    predicted = {
        ("R1", "pathway:glycolysis"),
        ("R3", "pathway:glycolysis"),
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
        "pathway:glycolysis": ConceptDefinition(
            "pathway:glycolysis",
            "pathway",
            "Glycolysis",
            parents=("pathway:carbohydrate",),
        ),
    }
    registry = ConceptRegistry(concepts)
    expected = {
        ("R1", "pathway:glycolysis"),
        ("R2", "pathway:glycolysis"),
        ("R3", "pathway:carbohydrate"),
    }
    predicted = {
        ("R1", "pathway:glycolysis"),
        ("R2", "pathway:carbohydrate"),
        ("R3", "pathway:glycolysis"),
    }

    metrics = hierarchy_aware_reaction_metrics(predicted, expected, registry)

    assert metrics["exact_recovered_reactions"] == 1
    assert metrics["specificity_preserving_recovered_reactions"] == 2
    assert metrics["broad_only_recovered_reactions"] == 1
    assert metrics["hierarchy_compatible_recall"] == 1.0
