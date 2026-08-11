"""Extract reproducible headline metrics from a MEMOTE HTML report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_memote_data(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    marker = "window.data = "
    try:
        start = text.index(marker) + len(marker)
    except ValueError as error:
        raise ValueError(f"No embedded MEMOTE data found in {path}") from error
    data, _ = json.JSONDecoder().raw_decode(text[start:])
    return data


def summarize_memote(path: Path) -> dict:
    data = load_memote_data(path)
    sections = {
        item["section"]: item["score"]
        for item in data.get("score", {}).get("sections", [])
    }
    tests = data.get("tests", {})
    return {
        "report": str(path),
        "timestamp": data.get("meta", {}).get("timestamp"),
        "total_score": data.get("score", {}).get("total_score"),
        "section_scores": sections,
        "tests_passed": sum(
            result == "passed"
            for test in tests.values()
            for result in (
                test.get("result", {}).values()
                if isinstance(test.get("result"), dict)
                else (test.get("result"),)
            )
        ),
        "tests_failed": sum(
            result == "failed"
            for test in tests.values()
            for result in (
                test.get("result", {}).values()
                if isinstance(test.get("result"), dict)
                else (test.get("result"),)
            )
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(summarize_memote(arguments.report), indent=2))


if __name__ == "__main__":
    main()
