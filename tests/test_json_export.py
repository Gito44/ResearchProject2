import gzip
import json
from dataclasses import replace
from pathlib import Path

import pytest

from semgem.database.sqlite import SemanticDatabase
from semgem.evidence.rules import CandidateEvidence, ScoredConcept, ScoredEvidence
from semgem.export import JsonCatalogExporter
from semgem.query import SemanticCatalog


@pytest.fixture
def catalog_path(tmp_path, schema_path, small_model, extracted):
    path = tmp_path / "catalog.sqlite"
    with SemanticDatabase(path, schema_path) as database:
        database.initialise()
        for model_id, source_file, content_hash, reactions in (
            ("test_model", "test.xml", "test-hash", extracted["reactions"]),
            (
                "second_model",
                "second.xml",
                "second-hash",
                [
                    replace(record, name="Second model biomass reaction")
                    for record in extracted["reactions"]
                ],
            ),
        ):
            model = small_model.copy()
            model.id = model_id
            database.import_model(
                model=model,
                source_file=source_file,
                content_hash=content_hash,
                reactions=reactions,
                metabolites=extracted["metabolites"],
                genes=extracted["genes"],
                stoichiometry=extracted["stoichiometry"],
                reaction_genes=extracted["reaction_genes"],
            )
        scored = []
        for (entity_id,) in database.conn.execute(
            "SELECT id FROM entities WHERE entity_type = 'reaction' ORDER BY id"
        ):
            candidate = CandidateEvidence(
                entity_id=entity_id,
                concept_id="objective:model_objective",
                evidence_code="objective_coefficient_nonzero",
                source="model",
                explanation="Nonzero objective coefficient",
                observed_value="1.0",
            )
            scored.append(
                ScoredConcept(
                    entity_id=entity_id,
                    concept_id="objective:model_objective",
                    preferred_label="Model objective",
                    confidence=1.0,
                    evidence=(ScoredEvidence(candidate=candidate, weight=1.0),),
                )
            )
        database.replace_semantic_concepts(scored)
    return path


def test_json_export_is_model_oriented_and_uses_stable_concept_ids(catalog_path):
    concepts_path = Path(__file__).parents[1] / "semgem" / "resources" / "concepts.toml"
    with SemanticCatalog(catalog_path) as catalog:
        document = JsonCatalogExporter(catalog, concepts_path).document(
            model_ids=["test_model"]
        )

    assert document["semgem"]["format"] == "semgem-semantic-catalog"
    assert document["semgem"]["schema_version"] == "1.0"
    assert document["catalog"]["model_count"] == 1
    assert "objective:model_objective" in document["concept_definitions"]
    model = document["models"][0]
    assert model["id"] == "test_model"
    reaction = model["entities"]["reactions"][0]
    assert reaction["id"] == "BIOMASS_TEST"
    assert reaction["metabolites"] == [
        {"id": "product_c", "coefficient": 1.0},
        {"id": "substrate_c", "coefficient": -1.0},
    ]
    assert reaction["genes"] == ["gene_a"]
    assert reaction["concepts"][0]["id"] == "objective:model_objective"
    assert reaction["concepts"][0]["evidence"][0]["code"] == (
        "objective_coefficient_nonzero"
    )
    assert "internal_id" not in json.dumps(document)


def test_json_export_can_omit_evidence_and_write_compact_json(
    catalog_path,
    tmp_path,
):
    concepts_path = Path(__file__).parents[1] / "semgem" / "resources" / "concepts.toml"
    output_path = tmp_path / "catalog.json"
    with SemanticCatalog(catalog_path) as catalog:
        exporter = JsonCatalogExporter(catalog, concepts_path)
        exporter.write(
            output_path,
            model_ids=["second_model"],
            include_evidence=False,
            compact=True,
        )

    document = json.loads(output_path.read_text(encoding="utf-8"))
    assert [model["id"] for model in document["models"]] == ["second_model"]
    concept = document["models"][0]["entities"]["reactions"][0]["concepts"][0]
    assert "evidence" not in concept
    assert "\n  " not in output_path.read_text(encoding="utf-8")


def test_json_export_can_write_gzip_without_changing_document(
    catalog_path,
    tmp_path,
):
    concepts_path = Path(__file__).parents[1] / "semgem" / "resources" / "concepts.toml"
    output_path = tmp_path / "catalog.json.gz"
    with SemanticCatalog(catalog_path) as catalog:
        JsonCatalogExporter(catalog, concepts_path).write(
            output_path,
            model_ids=["test_model"],
            compact=True,
            compress=True,
        )

    with gzip.open(output_path, "rt", encoding="utf-8") as file:
        document = json.load(file)

    assert document["semgem"]["format"] == "semgem-semantic-catalog"
    assert [model["id"] for model in document["models"]] == ["test_model"]
    assert output_path.read_bytes().startswith(b"\x1f\x8b")
