import sqlite3

import cobra
from typer.testing import CliRunner

from semgem.cli import app


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
