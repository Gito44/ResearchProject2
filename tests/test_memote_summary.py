import json

from evaluation.summarize_memote import load_memote_data, summarize_memote


def test_memote_summary_reads_embedded_report_data(tmp_path):
    payload = {
        "meta": {"timestamp": "2026-08-09"},
        "tests": {
            "one": {"result": "passed"},
            "parameterized": {"result": {"a": "passed", "b": "failed"}},
        },
        "score": {
            "sections": [{"section": "annotation_rxn", "score": 0.75}],
            "total_score": 0.5,
        },
    }
    report = tmp_path / "report.html"
    report.write_text(
        f"<script>window.data = {json.dumps(payload)};</script>",
        encoding="utf-8",
    )

    assert load_memote_data(report) == payload
    summary = summarize_memote(report)
    assert summary["total_score"] == 0.5
    assert summary["section_scores"]["annotation_rxn"] == 0.75
    assert summary["tests_passed"] == 2
    assert summary["tests_failed"] == 1
