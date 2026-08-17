import sqlite3

import cobra
import pytest

from semgem.core.records import (
    EnrichmentAssertionRecord,
    EntityAssertionEvidenceRecord,
    ExternalTermRecord,
    ExternalTermRelationshipRecord,
    ProviderRelationshipEvidenceRecord,
)
from semgem.database.sqlite import (
    DuplicateModelError,
    EntityTypeError,
    IncompatibleSchemaError,
    ModelIdentityConflictError,
    SemanticDatabase,
)
from semgem.evidence.rules import CandidateEvidence, ScoredConcept, ScoredEvidence
from semgem.extract.extractor import Extractor


def _import(db, model, extracted, content_hash="hash-one"):
    return db.import_model(
        model=model,
        source_file="test.xml",
        content_hash=content_hash,
        reactions=extracted["reactions"],
        metabolites=extracted["metabolites"],
        genes=extracted["genes"],
        stoichiometry=extracted["stoichiometry"],
        reaction_genes=extracted["reaction_genes"],
    )


@pytest.fixture
def database(tmp_path, schema_path):
    db = SemanticDatabase(tmp_path / "catalog.sqlite", schema_path)
    db.initialise()
    yield db
    db.close()


def test_initialisation_creates_the_agreed_tables(database):
    rows = database.conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    names = {row[0] for row in rows}
    assert {
        "models",
        "entities",
        "reactions",
        "metabolites",
        "genes",
        "reaction_metabolites",
        "reaction_genes",
        "annotations",
        "external_terms",
        "external_term_relationships",
        "provider_relationship_evidence",
        "enrichment_runs",
        "enrichment_assertions",
        "entity_assertion_evidence",
        "semantic_concepts",
        "concept_evidence",
    } <= names


def test_evidence_rows_expose_compartment_transport_structure(database):
    model = cobra.Model("transport_model")
    model.compartments = {"c": "Cytosol", "m": "Mitochondria"}
    pyruvate_c = cobra.Metabolite(
        "pyr_c",
        name="Pyruvate",
        compartment="c",
    )
    pyruvate_m = cobra.Metabolite(
        "pyr_m",
        name="Pyruvate",
        compartment="m",
    )
    reaction = cobra.Reaction("PYRtm", name="Pyruvate transport")
    reaction.add_metabolites({pyruvate_c: -1, pyruvate_m: 1})
    model.add_reactions([reaction])
    extractor = Extractor(model)

    database.import_model(
        model=model,
        source_file="transport.xml",
        content_hash="transport-hash",
        reactions=extractor.extract_reactions(),
        metabolites=extractor.extract_metabolites(),
        genes=extractor.extract_genes(),
        stoichiometry=extractor.extract_stoichiometry(),
        reaction_genes=extractor.extract_reaction_genes(),
    )

    row = next(
        item
        for item in database.evidence_entity_rows()
        if item["entity_type"] == "reaction"
    )

    assert row["has_transport_signature"] is True
    assert row["transport_compartment_names"] == "Cytosol Mitochondria"
    assert row["transported_metabolites"] == "pyr"


def test_old_schema_is_rejected_with_a_clear_error(tmp_path, schema_path):
    db_path = tmp_path / "old.sqlite"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE models (id INTEGER PRIMARY KEY, model_id TEXT)"
    )
    connection.close()

    database = SemanticDatabase(db_path, schema_path)
    with pytest.raises(IncompatibleSchemaError, match="version 6 is required"):
        database.initialise()
    database.close()


def test_partial_current_schema_is_rejected_with_a_clear_error(
    tmp_path,
    schema_path,
):
    db_path = tmp_path / "partial.sqlite"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE models (
            id INTEGER PRIMARY KEY,
            original_id TEXT,
            name TEXT,
            source_file TEXT,
            content_hash TEXT,
            compartments_json TEXT
        );
        CREATE TABLE semantic_concepts (
            id INTEGER PRIMARY KEY,
            entity_id INTEGER,
            concept_name TEXT,
            confidence REAL
        );
        PRAGMA user_version = 6;
        """
    )
    connection.close()

    database = SemanticDatabase(db_path, schema_path)
    with pytest.raises(IncompatibleSchemaError, match="semantic-label"):
        database.initialise()
    database.close()


def test_complete_model_import_uses_shared_entity_ids(
    database, small_model, extracted
):
    _import(database, small_model, extracted)

    entity_counts = dict(
        database.conn.execute(
            "SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type"
        ).fetchall()
    )
    assert entity_counts == {"reaction": 1, "metabolite": 2, "gene": 1}
    assert database.conn.execute("SELECT COUNT(*) FROM reactions").fetchone()[0] == 1
    assert database.conn.execute("SELECT COUNT(*) FROM reaction_genes").fetchone()[0] == 1
    assert database.conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_catalog_metadata_round_trips_json_values(database):
    database.set_catalog_metadata(
        {
            "subsystem_evidence_enabled": False,
            "concepts_sha256": "abc123",
        }
    )

    assert database.catalog_metadata() == {
        "concepts_sha256": "abc123",
        "subsystem_evidence_enabled": False,
    }


def test_annotation_lists_are_normalised_to_individual_rows(
    database, small_model, extracted
):
    _import(database, small_model, extracted)
    rhea = database.conn.execute(
        """
        SELECT a.identifier
        FROM annotations AS a
        JOIN entities AS e ON e.id = a.entity_id
        WHERE e.original_id = 'BIOMASS_TEST' AND a.source = 'rhea'
        ORDER BY a.identifier
        """
    ).fetchall()
    assert rhea == [("12345",), ("67890",)]


def test_scored_conclusions_store_fixed_evidence_and_provenance(
    database, small_model, extracted
):
    _import(database, small_model, extracted)
    entity_id = database.conn.execute(
        "SELECT id FROM entities WHERE original_id = 'BIOMASS_TEST'"
    ).fetchone()[0]
    candidate = CandidateEvidence(
        entity_id=entity_id,
        concept_id="objective:model_objective",
        evidence_code="objective_coefficient_nonzero",
        source="model",
        explanation="Nonzero objective coefficient",
        observed_value="1.0",
    )
    database.replace_semantic_concepts(
        [
            ScoredConcept(
                entity_id=entity_id,
                concept_id="objective:model_objective",
                preferred_label="Model objective",
                confidence=1.0,
                evidence=(ScoredEvidence(candidate=candidate, weight=1.0),),
            )
        ]
    )
    row = database.conn.execute(
        """
        SELECT evidence_code, source, observed_value
        FROM concept_evidence
        """
    ).fetchone()
    assert row == ("objective_coefficient_nonzero", "model", "1.0")


def test_duplicate_model_is_rejected_without_adding_rows(
    database, small_model, extracted
):
    _import(database, small_model, extracted)
    with pytest.raises(DuplicateModelError):
        _import(database, small_model, extracted)

    assert database.conn.execute("SELECT COUNT(*) FROM models").fetchone()[0] == 1
    assert database.conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 4


def test_same_model_id_with_different_content_is_rejected(
    database, small_model, extracted
):
    _import(database, small_model, extracted, content_hash="hash-one")
    with pytest.raises(ModelIdentityConflictError):
        _import(database, small_model, extracted, content_hash="hash-two")


def test_different_model_id_with_same_content_warns_and_imports(
    database, small_model, extracted
):
    _import(database, small_model, extracted, content_hash="shared-hash")
    second_model = small_model.copy()
    second_model.id = "second_model"

    with pytest.warns(UserWarning, match="identical"):
        _import(database, second_model, extracted, content_hash="shared-hash")

    assert database.conn.execute("SELECT COUNT(*) FROM models").fetchone()[0] == 2


def test_failed_import_rolls_back_the_whole_model(database, small_model, extracted):
    duplicate_reactions = extracted["reactions"] * 2
    with pytest.raises(sqlite3.IntegrityError):
        database.import_model(
            model=small_model,
            source_file="test.xml",
            content_hash="hash-one",
            reactions=duplicate_reactions,
            metabolites=extracted["metabolites"],
            genes=extracted["genes"],
            stoichiometry=extracted["stoichiometry"],
            reaction_genes=extracted["reaction_genes"],
        )

    assert database.conn.execute("SELECT COUNT(*) FROM models").fetchone()[0] == 0
    assert database.conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 0


def test_deleting_model_cascades_to_all_dependent_rows(
    database, small_model, extracted
):
    model_id = _import(database, small_model, extracted)
    with database.conn:
        database.conn.execute("DELETE FROM models WHERE id = ?", (model_id,))

    for table in (
        "entities",
        "reactions",
        "metabolites",
        "genes",
        "reaction_metabolites",
        "reaction_genes",
        "annotations",
        "semantic_concepts",
        "concept_evidence",
    ):
        assert database.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_entity_type_validation_rejects_wrong_type(
    database, small_model, extracted
):
    model_id = _import(database, small_model, extracted)
    metabolite_id = database.conn.execute(
        """
        SELECT e.id
        FROM entities AS e
        WHERE e.model_id = ? AND e.entity_type = 'metabolite'
        LIMIT 1
        """,
        (model_id,),
    ).fetchone()[0]

    with pytest.raises(EntityTypeError):
        database._assert_entity_type(metabolite_id, "reaction")


def test_enrichment_stores_shared_terms_relationships_and_evidence(
    database, small_model, extracted
):
    _import(database, small_model, extracted)
    entity_id, annotation_id = database.conn.execute(
        """
        SELECT e.id, a.id
        FROM entities AS e
        JOIN annotations AS a ON a.entity_id = e.id
        WHERE e.original_id = 'BIOMASS_TEST'
          AND a.source = 'sbo'
          AND a.identifier = 'SBO:0000629'
        """
    ).fetchone()

    database.store_enrichment(
        terms=[
            ExternalTermRecord(
                source="sbo",
                identifier="SBO:0000629",
                term_type="interaction",
                name="biomass production",
                source_version="2021-08-28",
            ),
            ExternalTermRecord(
                source="sbo",
                identifier="SBO:0000375",
                term_type="interaction",
                name="process",
                source_version="2021-08-28",
            ),
        ],
        relationships=[
            ExternalTermRelationshipRecord(
                subject_source="sbo",
                subject_identifier="SBO:0000629",
                predicate="is_a",
                object_source="sbo",
                object_identifier="SBO:0000375",
                evidence=(
                    ProviderRelationshipEvidenceRecord(
                        provider="sbo",
                        retrieval_method="packaged_obo",
                        resource_version="2021-08-28",
                    ),
                ),
            )
        ],
        assertions=[
            EnrichmentAssertionRecord(
                entity_id=entity_id,
                predicate="has_sbo_term",
                term_source="sbo",
                term_identifier="SBO:0000629",
                evidence=(
                    EntityAssertionEvidenceRecord(
                        provider="sbo",
                        evidence_type="source_model_annotation",
                        source_annotation_id=annotation_id,
                        source_identifier="SBO:0000629",
                        retrieval_method="packaged_obo",
                        resource_version="2021-08-28",
                    ),
                ),
            )
        ],
    )

    assert database.conn.execute("SELECT COUNT(*) FROM external_terms").fetchone()[0] == 2
    assert database.conn.execute(
        "SELECT COUNT(*) FROM external_term_relationships"
    ).fetchone()[0] == 1
    assert database.conn.execute(
        "SELECT COUNT(*) FROM enrichment_assertions"
    ).fetchone()[0] == 1
    evidence = database.conn.execute(
        """
        SELECT evidence_type, source_annotation_id, resource_version
        FROM entity_assertion_evidence
        """
    ).fetchone()
    assert evidence == (
        "source_model_annotation",
        annotation_id,
        "2021-08-28",
    )
    assert database.conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_enrichment_refresh_reuses_terms_and_replaces_evidence(
    database, small_model, extracted
):
    _import(database, small_model, extracted)
    entity_id = database.conn.execute(
        "SELECT id FROM entities WHERE original_id = 'BIOMASS_TEST'"
    ).fetchone()[0]
    term = ExternalTermRecord(
        source="sbo",
        identifier="SBO:0000629",
        term_type="interaction",
        name="biomass production",
    )

    first = EnrichmentAssertionRecord(
        entity_id=entity_id,
        predicate="has_sbo_term",
        term_source="sbo",
        term_identifier="SBO:0000629",
        evidence=(
            EntityAssertionEvidenceRecord(
                provider="sbo",
                evidence_type="old",
                retrieval_method="packaged_obo",
            ),
        ),
    )
    refreshed = EnrichmentAssertionRecord(
        entity_id=entity_id,
        predicate="has_sbo_term",
        term_source="sbo",
        term_identifier="SBO:0000629",
        evidence=(
            EntityAssertionEvidenceRecord(
                provider="sbo",
                evidence_type="refreshed",
                retrieval_method="packaged_obo",
            ),
        ),
    )

    database.store_enrichment([term], [], [first])
    database.store_enrichment([term], [], [refreshed])

    assert database.conn.execute("SELECT COUNT(*) FROM external_terms").fetchone()[0] == 1
    assert database.conn.execute(
        "SELECT COUNT(*) FROM enrichment_assertions"
    ).fetchone()[0] == 1
    assert database.conn.execute(
        "SELECT evidence_type FROM entity_assertion_evidence"
    ).fetchall() == [("refreshed",)]


def test_enrichment_refresh_preserves_evidence_from_other_providers(
    database, small_model, extracted
):
    _import(database, small_model, extracted)
    entity_id = database.conn.execute(
        "SELECT id FROM entities WHERE original_id = 'BIOMASS_TEST'"
    ).fetchone()[0]
    term = ExternalTermRecord(
        source="sbo",
        identifier="SBO:0000629",
        term_type="interaction",
    )
    initial = EnrichmentAssertionRecord(
        entity_id=entity_id,
        predicate="has_semantic_term",
        term_source="sbo",
        term_identifier="SBO:0000629",
        evidence=(
            EntityAssertionEvidenceRecord(
                provider="sbo",
                evidence_type="old_sbo",
                retrieval_method="packaged_obo",
            ),
            EntityAssertionEvidenceRecord(
                provider="metanetx",
                evidence_type="cross_reference",
                retrieval_method="local_cross_reference",
            ),
        ),
    )
    refreshed = EnrichmentAssertionRecord(
        entity_id=entity_id,
        predicate="has_semantic_term",
        term_source="sbo",
        term_identifier="SBO:0000629",
        evidence=(
            EntityAssertionEvidenceRecord(
                provider="sbo",
                evidence_type="refreshed_sbo",
                retrieval_method="packaged_obo",
            ),
        ),
    )

    database.store_enrichment([term], [], [initial])
    database.store_enrichment([term], [], [refreshed])

    evidence = database.conn.execute(
        """
        SELECT provider, evidence_type
        FROM entity_assertion_evidence
        ORDER BY provider
        """
    ).fetchall()
    assert evidence == [
        ("metanetx", "cross_reference"),
        ("sbo", "refreshed_sbo"),
    ]


def test_deleting_model_removes_assertions_but_preserves_shared_terms(
    database, small_model, extracted
):
    model_id = _import(database, small_model, extracted)
    entity_id = database.conn.execute(
        "SELECT id FROM entities WHERE original_id = 'BIOMASS_TEST'"
    ).fetchone()[0]
    database.store_enrichment(
        [
            ExternalTermRecord(
                source="sbo",
                identifier="SBO:0000629",
                term_type="interaction",
            )
        ],
        [],
        [
            EnrichmentAssertionRecord(
                entity_id=entity_id,
                predicate="has_sbo_term",
                term_source="sbo",
                term_identifier="SBO:0000629",
                evidence=(
                    EntityAssertionEvidenceRecord(
                        provider="sbo",
                        evidence_type="source_model_annotation",
                        retrieval_method="packaged_obo",
                    ),
                ),
            )
        ],
    )

    with database.conn:
        database.conn.execute("DELETE FROM models WHERE id = ?", (model_id,))

    assert database.conn.execute(
        "SELECT COUNT(*) FROM enrichment_assertions"
    ).fetchone()[0] == 0
    assert database.conn.execute(
        "SELECT COUNT(*) FROM entity_assertion_evidence"
    ).fetchone()[0] == 0
    assert database.conn.execute("SELECT COUNT(*) FROM external_terms").fetchone()[0] == 1


def test_failed_enrichment_rolls_back_all_new_rows(
    database, small_model, extracted
):
    _import(database, small_model, extracted)

    with pytest.raises(ValueError, match="is not stored"):
        database.store_enrichment(
            [
                ExternalTermRecord(
                    source="sbo",
                    identifier="SBO:0000629",
                    term_type="interaction",
                )
            ],
            [
                ExternalTermRelationshipRecord(
                    subject_source="sbo",
                    subject_identifier="SBO:0000629",
                    predicate="is_a",
                    object_source="sbo",
                    object_identifier="SBO:9999999",
                )
            ],
            [],
        )

    assert database.conn.execute("SELECT COUNT(*) FROM external_terms").fetchone()[0] == 0


def test_external_relationship_cache_is_shared_across_models(
    database, small_model, extracted
):
    _import(database, small_model, extracted, content_hash="first")
    second_model = small_model.copy()
    second_model.id = "second_model"
    _import(database, second_model, extracted, content_hash="second")

    database.store_enrichment(
        terms=[
            ExternalTermRecord(
                source="kegg.reaction",
                identifier="R00001",
                term_type="reaction",
            ),
            ExternalTermRecord(
                source="kegg.pathway",
                identifier="map00010",
                term_type="pathway",
                name="Glycolysis / Gluconeogenesis",
            ),
        ],
        relationships=[
            ExternalTermRelationshipRecord(
                subject_source="kegg.reaction",
                subject_identifier="R00001",
                predicate="belongs_to_pathway",
                object_source="kegg.pathway",
                object_identifier="map00010",
                evidence=(
                    ProviderRelationshipEvidenceRecord(
                        provider="kegg",
                        retrieval_method="rest_link",
                        source_identifier="R00001",
                        retrieved_at="2026-07-27T12:00:00Z",
                    ),
                ),
            )
        ],
        assertions=[],
    )

    assert database.conn.execute("SELECT COUNT(*) FROM external_terms").fetchone()[0] == 2
    assert database.conn.execute(
        "SELECT COUNT(*) FROM external_term_relationships"
    ).fetchone()[0] == 1
    assert database.conn.execute(
        "SELECT provider FROM provider_relationship_evidence"
    ).fetchall() == [("kegg",)]


def test_enrichment_run_records_completion_and_counts(database):
    run_id = database.start_enrichment_run(
        provider="kegg",
        started_at="2026-07-27T12:00:00Z",
        resource_version="REST",
    )
    database.finish_enrichment_run(
        run_id=run_id,
        status="partial",
        completed_at="2026-07-27T12:01:00Z",
        requested_count=10,
        resolved_count=8,
        unresolved_count=2,
        error_summary="Two identifiers were not resolved.",
    )

    row = database.conn.execute(
        """
        SELECT provider, status, requested_count, resolved_count,
               unresolved_count, error_summary
        FROM enrichment_runs
        WHERE id = ?
        """,
        (run_id,),
    ).fetchone()
    assert row == (
        "kegg",
        "partial",
        10,
        8,
        2,
        "Two identifiers were not resolved.",
    )


def test_enrichment_run_rejects_invalid_finished_status(database):
    run_id = database.start_enrichment_run(
        provider="sbo",
        started_at="2026-07-27T12:00:00Z",
    )

    with pytest.raises(ValueError, match="completed, partial, or failed"):
        database.finish_enrichment_run(
            run_id=run_id,
            status="running",
            completed_at="2026-07-27T12:01:00Z",
            requested_count=0,
            resolved_count=0,
            unresolved_count=0,
        )
