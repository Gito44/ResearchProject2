from dataclasses import replace

import pytest

from semgem.database.sqlite import SemanticDatabase
from semgem.evidence.rules import CandidateEvidence, ScoredConcept, ScoredEvidence
from semgem.query import (
    ConceptNotFoundError,
    EntityNotFoundError,
    SemanticCatalog,
)


@pytest.fixture
def catalog_path(tmp_path, schema_path, small_model, extracted):
    path = tmp_path / "catalog.sqlite"
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
        )
        entity_ids = [
            row[0]
            for row in database.conn.execute(
                """
                SELECT e.id
                FROM entities AS e
                WHERE e.entity_type = 'reaction'
                ORDER BY e.id
                """
            ).fetchall()
        ]
        scored = []
        for entity_id in entity_ids:
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


def test_catalog_lists_models(catalog_path):
    with SemanticCatalog(catalog_path) as catalog:
        models = catalog.list_models()

    assert [model.original_id for model in models] == ["second_model", "test_model"]
    assert models[1].content_hash == "test-hash"


def test_catalog_reports_statistics_and_actionable_coverage(catalog_path):
    with SemanticCatalog(catalog_path) as catalog:
        statistics = catalog.statistics()
        coverage = catalog.coverage()

    assert statistics.model_count == 2
    assert statistics.reaction_count == 2
    assert statistics.semantic_assignment_count == 2
    assert coverage.total_reactions == 2
    assert coverage.pathway_reactions == 0
    assert coverage.actionable_non_pathway_reactions == 2
    assert coverage.actionable_reactions == 2
    assert coverage.generic_only_reactions == 0
    assert coverage.unclassified_reactions == 0


def test_catalog_filters_concept_assignments_and_unclassified_reactions(catalog_path):
    with SemanticCatalog(catalog_path) as catalog:
        assignments = catalog.get_concept_assignments(
            "objective:model_objective",
            model_id="test_model",
            minimum_confidence=1.0,
        )
        unclassified = catalog.list_unclassified_reactions()

    assert len(assignments) == 1
    assert assignments[0].entity.model_id == "test_model"
    assert assignments[0].concept.name == "objective:model_objective"
    assert unclassified == []


def test_catalog_reports_missing_model_for_aggregate_queries(catalog_path):
    with SemanticCatalog(catalog_path) as catalog:
        with pytest.raises(EntityNotFoundError, match="Model not found"):
            catalog.coverage("missing")


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
            "objective:model_objective",
        )

    assert [(concept.name, concept.confidence) for concept in concepts] == [
        ("objective:model_objective", 1.0)
    ]
    assert concepts[0].preferred_label == "Model objective"
    assert explanation.name == "objective:model_objective"
    assert explanation.preferred_label == "Model objective"
    assert explanation.evidence[0].evidence_code == "objective_coefficient_nonzero"
    assert explanation.evidence[0].observed_value == "1.0"


def test_catalog_reports_missing_entities_and_concepts(catalog_path):
    with SemanticCatalog(catalog_path) as catalog:
        with pytest.raises(EntityNotFoundError, match="missing"):
            catalog.get_entity("test_model", "reaction", "missing")

        with pytest.raises(
            ConceptNotFoundError,
            match="objective:biomass_production",
        ):
            catalog.explain_concept(
                "test_model",
                "reaction",
                "BIOMASS_TEST",
                "objective:biomass_production",
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
        concept_results = catalog.search("objective:model_objective")
        label_results = catalog.search("model objective")

    assert [result.entity.model_id for result in name_results] == ["second_model"]
    assert name_results[0].matches[0].field == "name"
    assert len(annotation_results) == 2
    assert annotation_results[0].matches[0].source == "kegg.reaction"
    assert len(concept_results) == 2
    assert concept_results[0].matches[0].field == "concept"
    assert len(label_results) == 2
    assert label_results[0].matches[0].field == "concept"


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
