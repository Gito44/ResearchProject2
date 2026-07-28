from evaluation.benchmark_subsystems import (
    classification_metrics,
    split_subsystems,
)


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
