import sqlite3

import cobra
import pytest
from typer.testing import CliRunner

from semgem.cli import app


@pytest.fixture
def cli_catalog(tmp_path, small_model):
    model_path = tmp_path / "model.xml"
    catalog_path = tmp_path / "catalog.sqlite"
    cobra.io.write_sbml_model(small_model, model_path)
    result = CliRunner().invoke(
        app,
        ["build", str(model_path), "--out", str(catalog_path)],
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
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Models imported: 2" in result.output

    with sqlite3.connect(catalog_path) as connection:
        models = connection.execute(
            "SELECT original_id FROM models ORDER BY original_id"
        ).fetchall()

    assert models == [("second_model",), ("test_model",)]


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


def test_models_command_lists_catalog_models(cli_catalog):
    result = CliRunner().invoke(app, ["models", str(cli_catalog)])

    assert result.exit_code == 0, result.output
    assert "test_model\tTest model" in result.output


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
        ["explain", *entity_options, "--concept", "objective_reaction"],
    )

    assert concepts_result.exit_code == 0, concepts_result.output
    assert "objective_reaction\tconfidence=1.000" in concepts_result.output
    assert explain_result.exit_code == 0, explain_result.output
    assert "objective_coefficient" in explain_result.output
    assert "matched=1.0" in explain_result.output


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
