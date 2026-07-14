from dataclasses import replace

import pytest

from semgem.database.sqlite import SemanticDatabase
from semgem.evidence.rules import EvidenceMatch, SemanticConcept
from semgem.query import (
    ConceptNotFoundError,
    EntityNotFoundError,
    SemanticCatalog,
)


@pytest.fixture
def catalog_path(tmp_path, schema_path, small_model, extracted):
    path = tmp_path / "catalog.sqlite"
    concept = SemanticConcept(
        concept_name="objective_reaction",
        entity_type="reaction",
        entity_id="BIOMASS_TEST",
        confidence=1.0,
        evidence=[
            EvidenceMatch(
                evidence_type="objective",
                target_field="objective_coefficient",
                matched_value="1.0",
                evidence_text="Nonzero objective coefficient",
                weight=1.0,
            )
        ],
    )
    with SemanticDatabase(path, schema_path) as database:
        database.initialise()
        database.import_model(
            model=small_model,
            source_file="test.xml",
            content_hash="test-hash",
            reactions=extracted["reactions"],
            metabolites=extracted["metabolites"],
            genes=extracted["genes"],
            stoichiometry=extracted["stoichiometry"],
            reaction_genes=extracted["reaction_genes"],
            concepts=[concept],
        )
        second_model = small_model.copy()
        second_model.id = "second_model"
        second_reactions = [
            replace(record, name="Second model biomass reaction")
            for record in extracted["reactions"]
        ]
        database.import_model(
            model=second_model,
            source_file="second.xml",
            content_hash="second-hash",
            reactions=second_reactions,
            metabolites=extracted["metabolites"],
            genes=extracted["genes"],
            stoichiometry=extracted["stoichiometry"],
            reaction_genes=extracted["reaction_genes"],
            concepts=[concept],
        )
    return path


def test_catalog_lists_models(catalog_path):
    with SemanticCatalog(catalog_path) as catalog:
        models = catalog.list_models()

    assert [model.original_id for model in models] == ["second_model", "test_model"]
    assert models[1].content_hash == "test-hash"


def test_catalog_resolves_entity_with_model_scope(catalog_path):
    with SemanticCatalog(catalog_path) as catalog:
        first = catalog.get_entity("test_model", "reaction", "BIOMASS_TEST")
        second = catalog.get_entity("second_model", "reaction", "BIOMASS_TEST")

    assert first.model_id == "test_model"
    assert first.entity_type == "reaction"
    assert first.name == "Test biomass reaction"
    assert second.model_id == "second_model"
    assert second.name == "Second model biomass reaction"


def test_catalog_returns_normalised_annotations(catalog_path):
    with SemanticCatalog(catalog_path) as catalog:
        annotations = catalog.get_annotations(
            "test_model", "reaction", "BIOMASS_TEST"
        )

    assert [(item.source, item.identifier) for item in annotations] == [
        ("kegg.reaction", "R00001"),
        ("rhea", "12345"),
        ("rhea", "67890"),
        ("sbo", "SBO:0000629"),
    ]


def test_catalog_lists_and_explains_concepts(catalog_path):
    with SemanticCatalog(catalog_path) as catalog:
        concepts = catalog.get_concepts(
            "test_model", "reaction", "BIOMASS_TEST"
        )
        explanation = catalog.explain_concept(
            "test_model",
            "reaction",
            "BIOMASS_TEST",
            "objective_reaction",
        )

    assert [(concept.name, concept.confidence) for concept in concepts] == [
        ("objective_reaction", 1.0)
    ]
    assert explanation.name == "objective_reaction"
    assert explanation.evidence[0].target_field == "objective_coefficient"
    assert explanation.evidence[0].matched_value == "1.0"


def test_catalog_reports_missing_entities_and_concepts(catalog_path):
    with SemanticCatalog(catalog_path) as catalog:
        with pytest.raises(EntityNotFoundError, match="missing"):
            catalog.get_entity("test_model", "reaction", "missing")

        with pytest.raises(ConceptNotFoundError, match="biomass_reaction"):
            catalog.explain_concept(
                "test_model",
                "reaction",
                "BIOMASS_TEST",
                "biomass_reaction",
            )


def test_catalog_rejects_unknown_entity_types(catalog_path):
    with SemanticCatalog(catalog_path) as catalog:
        with pytest.raises(ValueError, match="Unknown entity type"):
            catalog.get_entity("test_model", "protein", "protein_a")


def test_catalog_does_not_create_a_missing_database(tmp_path):
    missing = tmp_path / "missing.sqlite"

    with pytest.raises(FileNotFoundError):
        SemanticCatalog(missing)

    assert not missing.exists()


def test_search_finds_same_entity_id_across_models(catalog_path):
    with SemanticCatalog(catalog_path) as catalog:
        results = catalog.search("biomass_test", entity_type="reaction")

    assert [result.entity.model_id for result in results] == [
        "second_model",
        "test_model",
    ]
    assert all(result.matches[0].field == "id" for result in results)


def test_search_matches_names_annotations_and_concepts(catalog_path):
    with SemanticCatalog(catalog_path) as catalog:
        name_results = catalog.search("second model biomass")
        annotation_results = catalog.search("R00001")
        concept_results = catalog.search("objective_reaction")

    assert [result.entity.model_id for result in name_results] == ["second_model"]
    assert name_results[0].matches[0].field == "name"
    assert len(annotation_results) == 2
    assert annotation_results[0].matches[0].source == "kegg.reaction"
    assert len(concept_results) == 2
    assert concept_results[0].matches[0].field == "concept"


def test_search_filters_model_annotation_source_and_limit(catalog_path):
    with SemanticCatalog(catalog_path) as catalog:
        filtered = catalog.search(
            "R00001",
            model_id="test_model",
            annotation_source="kegg.reaction",
        )
        limited = catalog.search("biomass", limit=1)

    assert len(filtered) == 1
    assert filtered[0].entity.model_id == "test_model"
    assert filtered[0].matches[0].source == "kegg.reaction"
    assert len(limited) == 1


def test_search_treats_sql_wildcards_as_literal_text(catalog_path):
    with SemanticCatalog(catalog_path) as catalog:
        results = catalog.search("%_")

    assert results == []
