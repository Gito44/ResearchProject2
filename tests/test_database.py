import sqlite3

import pytest

from semgem.database.sqlite import (
    DuplicateModelError,
    EntityTypeError,
    IncompatibleSchemaError,
    ModelIdentityConflictError,
    SemanticDatabase,
)
from semgem.evidence.engine import EvidenceEngine
from semgem.evidence.rules import ConceptDefinition, EvidenceRule


def _concepts(extracted):
    definition = ConceptDefinition(
        name="objective_reaction",
        entity_type="reaction",
        description="Objective",
        minimum_score=1.0,
        rules=[
            EvidenceRule(
                evidence_type="objective",
                target_field="objective_coefficient",
                operator="nonzero",
                weight=1.0,
                text="Nonzero objective coefficient",
            )
        ],
    )
    return EvidenceEngine([definition]).classify_reactions(extracted["reactions"])


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
        concepts=_concepts(extracted),
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
        "semantic_concepts",
        "concept_evidence",
    } <= names


def test_old_schema_is_rejected_with_a_clear_error(tmp_path, schema_path):
    db_path = tmp_path / "old.sqlite"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE models (id INTEGER PRIMARY KEY, model_id TEXT)"
    )
    connection.close()

    database = SemanticDatabase(db_path, schema_path)
    with pytest.raises(IncompatibleSchemaError, match="older SemGEM schema"):
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


def test_evidence_records_target_and_matched_value(database, small_model, extracted):
    _import(database, small_model, extracted)
    row = database.conn.execute(
        "SELECT target_field, matched_value FROM concept_evidence"
    ).fetchone()
    assert row == ("objective_coefficient", "1.0")


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
            concepts=[],
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
