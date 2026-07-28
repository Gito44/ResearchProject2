from pathlib import Path

import pytest

from evaluation.evaluate_benchmark import load_benchmark, metrics, wilson_interval


def test_metrics_reports_precision_recall_and_f1():
    expected = {("m", "r1", "c"), ("m", "r2", "c")}
    predicted = {("m", "r1", "c"), ("m", "r3", "c")}

    result = metrics(expected, predicted)

    assert result["true_positive"] == 1
    assert result["false_positive"] == 1
    assert result["false_negative"] == 1
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5
    assert result["f1"] == 0.5


def test_wilson_interval_is_bounded_and_reflects_sample_uncertainty():
    lower, upper = wilson_interval(93, 93)

    assert 0.95 < lower < 1.0
    assert upper == pytest.approx(1.0)


def test_curated_benchmark_is_nonempty_and_internally_consistent():
    path = Path(__file__).parents[1] / "evaluation/curated_benchmark.toml"

    _, scoped, entities, expected = load_benchmark(path)

    assert len(entities) == 118
    assert len(expected) == 118
    assert all(item[2] in scoped for item in expected)
