import io
import gzip
import json
import sqlite3

import cobra
import pytest
from typer.testing import CliRunner

from semgem.cli import app, import_model
from semgem.resources_manager import ResourceManager


@pytest.fixture
def cli_catalog(tmp_path, small_model):
    model_path = tmp_path / "model.xml"
    catalog_path = tmp_path / "catalog.sqlite"
    cobra.io.write_sbml_model(small_model, model_path)
    result = CliRunner().invoke(
        app,
        [
            "build", str(model_path), "--out", str(catalog_path),
            "--no-rhea", "--no-metanetx",
            "--resource-dir", str(tmp_path / "resources"),
        ],
    )
    assert result.exit_code == 0, result.output
    return catalog_path


def test_build_imports_multiple_models_into_one_catalog(tmp_path, small_model):
    first_path = tmp_path / "first.xml"
    second_path = tmp_path / "second.xml"
    catalog_path = tmp_path / "catalog.sqlite"

    cobra.io.write_sbml_model(small_model, first_path)
    second_model = small_model.copy()
    second_model.id = "second_model"
    cobra.io.write_sbml_model(second_model, second_path)

    result = CliRunner().invoke(
        app,
        [
            "build",
            str(first_path),
            str(second_path),
            "--out",
            str(catalog_path),
            "--no-rhea",
            "--no-metanetx",
            "--resource-dir",
            str(tmp_path / "resources"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Models imported: 2" in result.output

    with sqlite3.connect(catalog_path) as connection:
        models = connection.execute(
            "SELECT original_id FROM models ORDER BY original_id"
        ).fetchall()

    assert models == [("second_model",), ("test_model",)]


def test_build_runs_bulk_sbo_enrichment_and_stores_explainable_conclusions(
    tmp_path, small_model
):
    first_path = tmp_path / "first.xml"
    second_path = tmp_path / "second.xml"
    catalog_path = tmp_path / "catalog.sqlite"
    cobra.io.write_sbml_model(small_model, first_path)
    second_model = small_model.copy()
    second_model.id = "second_model"
    cobra.io.write_sbml_model(second_model, second_path)

    result = CliRunner().invoke(
        app,
        [
            "build",
            str(first_path),
            str(second_path),
            "--out",
            str(catalog_path),
            "--no-kegg",
            "--no-rhea",
            "--no-metanetx",
            "--resource-dir",
            str(tmp_path / "resources"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "SBO enrichment: completed (resolved 1/1" in result.output
    with sqlite3.connect(catalog_path) as connection:
        assert connection.execute(
            """
            SELECT COUNT(*) FROM external_terms
            WHERE source = 'sbo' AND identifier = 'SBO:0000629'
            """
        ).fetchone()[0] == 1
        assert connection.execute(
            """
            SELECT COUNT(*) FROM enrichment_assertions
            WHERE predicate = 'has_sbo_term'
            """
        ).fetchone()[0] == 2
        assigned = connection.execute(
            """
            SELECT COUNT(*) FROM semantic_concepts
            WHERE concept_name = 'objective:biomass_production'
            """
        ).fetchone()[0]
    assert assigned == 2


def test_build_discovers_models_recursively_and_deduplicates_paths(
    tmp_path, small_model
):
    models_path = tmp_path / "models"
    nested_path = models_path / "nested"
    nested_path.mkdir(parents=True)
    first_path = models_path / "first.xml"
    second_path = nested_path / "second.sbml"
    catalog_path = tmp_path / "catalog.sqlite"

    cobra.io.write_sbml_model(small_model, first_path)
    second_model = small_model.copy()
    second_model.id = "second_model"
    cobra.io.write_sbml_model(second_model, second_path)
    (models_path / "notes.txt").write_text("not a model", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "build",
            str(models_path),
            str(first_path),
            "--out",
            str(catalog_path),
            "--no-rhea",
            "--no-metanetx",
            "--resource-dir",
            str(tmp_path / "resources"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Models imported: 2" in result.output

    with sqlite3.connect(catalog_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM models").fetchone()[0]

    assert count == 2


def test_build_rejects_a_directory_without_supported_models(tmp_path):
    empty_path = tmp_path / "empty"
    empty_path.mkdir()
    (empty_path / "notes.txt").write_text("not a model", encoding="utf-8")

    result = CliRunner().invoke(app, ["build", str(empty_path)])

    assert result.exit_code == 2
    assert "No supported SBML model files were found" in result.output


def test_import_model_reports_the_source_file_for_an_empty_model_id(
    tmp_path,
    monkeypatch,
):
    model_path = tmp_path / "invalid.xml"
    model = cobra.Model("")
    monkeypatch.setattr("semgem.cli.load_sbml_model", lambda _: model)

    with pytest.raises(ValueError, match=r"invalid\.xml.*no usable SBML model ID"):
        import_model(model_path, database=None)


def test_build_without_kegg_recommends_a_new_catalogue(tmp_path, small_model):
    model_path = tmp_path / "model.xml"
    catalog_path = tmp_path / "catalog.sqlite"
    cobra.io.write_sbml_model(small_model, model_path)

    result = CliRunner().invoke(
        app,
        [
            "build",
            str(model_path),
            "--out",
            str(catalog_path),
            "--no-kegg",
            "--no-rhea",
            "--no-metanetx",
            "--resource-dir",
            str(tmp_path / "resources"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Build a new catalogue with --kegg" in result.output


def test_resources_command_reports_managed_cache_status(tmp_path):
    manager = ResourceManager(
        tmp_path,
        opener=lambda request, timeout: io.BytesIO(b"xref\n"),
    )
    manager.ensure("rhea_xref")

    result = CliRunner().invoke(
        app,
        ["resources", "--resource-dir", str(tmp_path), "--format", "json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    statuses = {item["key"]: item for item in payload["resources"]}
    assert statuses["rhea_xref"]["verified"] is True
    assert statuses["metanetx_reac_xref"]["available"] is False


def test_models_command_lists_catalog_models(cli_catalog):
    result = CliRunner().invoke(app, ["models", str(cli_catalog)])

    assert result.exit_code == 0, result.output
    assert "test_model\tTest model" in result.output


def test_summary_and_coverage_commands_report_actionable_results(cli_catalog):
    runner = CliRunner()
    summary_result = runner.invoke(app, ["summary", str(cli_catalog)])
    coverage_result = runner.invoke(app, ["coverage", str(cli_catalog)])

    assert summary_result.exit_code == 0, summary_result.output
    assert "models\t1" in summary_result.output
    assert "reactions\t1" in summary_result.output
    assert coverage_result.exit_code == 0, coverage_result.output
    assert "actionable_total\t1\t100.00%" in coverage_result.output
    assert "pathway\t0\t0.00%" in coverage_result.output


def test_analysis_commands_support_machine_readable_json(cli_catalog):
    runner = CliRunner()
    coverage_result = runner.invoke(
        app, ["coverage", str(cli_catalog), "--format", "json"]
    )
    concept_result = runner.invoke(
        app,
        [
            "get-concept",
            str(cli_catalog),
            "--concept",
            "objective:model_objective",
            "--format",
            "json",
        ],
    )

    assert coverage_result.exit_code == 0, coverage_result.output
    assert json.loads(coverage_result.output)["actionable_coverage"] == 1.0
    assert concept_result.exit_code == 0, concept_result.output
    assert json.loads(concept_result.output)[0]["concept"]["id"] == (
        "objective:model_objective"
    )


def test_export_command_writes_model_filtered_json(cli_catalog, tmp_path):
    output_path = tmp_path / "export.json"
    result = CliRunner().invoke(
        app,
        [
            "export",
            str(cli_catalog),
            "--out",
            str(output_path),
            "--model",
            "test_model",
        ],
    )

    assert result.exit_code == 0, result.output
    document = json.loads(output_path.read_text(encoding="utf-8"))
    assert [model["id"] for model in document["models"]] == ["test_model"]
    assert document["catalog"]["metadata"]["subsystem_evidence_enabled"] is True
    assert document["catalog"]["metadata"]["concepts_sha256"]
    assert document["models"][0]["entities"]["reactions"][0]["concepts"]


def test_export_command_infers_gzip_from_output_suffix(cli_catalog, tmp_path):
    output_path = tmp_path / "export.json.gz"
    result = CliRunner().invoke(
        app,
        ["export", str(cli_catalog), "--out", str(output_path), "--compact"],
    )

    assert result.exit_code == 0, result.output
    with gzip.open(output_path, "rt", encoding="utf-8") as file:
        document = json.load(file)
    assert document["semgem"]["format"] == "semgem-semantic-catalog"


def test_get_concept_and_unclassified_commands(cli_catalog):
    runner = CliRunner()
    concept_result = runner.invoke(
        app,
        [
            "get-concept",
            str(cli_catalog),
            "--concept",
            "objective:model_objective",
        ],
    )
    unclassified_result = runner.invoke(
        app, ["unclassified", str(cli_catalog)]
    )

    assert concept_result.exit_code == 0, concept_result.output
    assert "test_model\treaction\tBIOMASS_TEST" in concept_result.output
    assert unclassified_result.exit_code == 0, unclassified_result.output
    assert "No unclassified reactions found." in unclassified_result.output


def test_providers_and_compare_commands(cli_catalog):
    runner = CliRunner()
    providers_result = runner.invoke(app, ["providers", str(cli_catalog)])
    compare_result = runner.invoke(
        app,
        [
            "compare",
            str(cli_catalog),
            "--model",
            "test_model",
            "--model",
            "missing",
        ],
    )

    assert providers_result.exit_code == 0, providers_result.output
    assert "sbo\tcompleted" in providers_result.output
    assert compare_result.exit_code == 1
    assert "Model not found: missing" in compare_result.output


def test_entity_command_shows_a_model_scoped_entity(cli_catalog):
    result = CliRunner().invoke(
        app,
        [
            "entity",
            str(cli_catalog),
            "--model",
            "test_model",
            "--type",
            "reaction",
            "--id",
            "BIOMASS_TEST",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "type\treaction" in result.output
    assert "name\tTest biomass reaction" in result.output


def test_annotations_command_lists_normalised_identifiers(cli_catalog):
    result = CliRunner().invoke(
        app,
        [
            "annotations",
            str(cli_catalog),
            "--model",
            "test_model",
            "--type",
            "reaction",
            "--id",
            "BIOMASS_TEST",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "kegg.reaction\tR00001" in result.output
    assert "sbo\tSBO:0000629" in result.output


def test_concepts_and_explain_commands_show_evidence(cli_catalog):
    runner = CliRunner()
    entity_options = [
        str(cli_catalog),
        "--model",
        "test_model",
        "--type",
        "reaction",
        "--id",
        "BIOMASS_TEST",
    ]

    concepts_result = runner.invoke(app, ["concepts", *entity_options])
    explain_result = runner.invoke(
        app,
        ["explain", *entity_options, "--concept", "objective:model_objective"],
    )

    assert concepts_result.exit_code == 0, concepts_result.output
    assert (
        "objective:model_objective\tModel objective\tconfidence=1.000"
        in concepts_result.output
    )
    assert explain_result.exit_code == 0, explain_result.output
    assert "objective_coefficient_nonzero" in explain_result.output
    assert "observed=1.0" in explain_result.output


def test_query_command_reports_missing_entity(cli_catalog):
    result = CliRunner().invoke(
        app,
        [
            "entity",
            str(cli_catalog),
            "--model",
            "test_model",
            "--type",
            "reaction",
            "--id",
            "missing",
        ],
    )

    assert result.exit_code == 1
    assert "Entity not found" in result.output


def test_search_command_finds_and_describes_matches(cli_catalog):
    result = CliRunner().invoke(
        app,
        [
            "search",
            str(cli_catalog),
            "R00001",
            "--type",
            "reaction",
            "--source",
            "kegg.reaction",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "test_model\treaction\tBIOMASS_TEST" in result.output
    assert "annotation[kegg.reaction]=R00001" in result.output
