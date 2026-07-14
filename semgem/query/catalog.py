import sqlite3
from pathlib import Path

from semgem.query.records import (
    AnnotationResult,
    ConceptExplanation,
    ConceptSummary,
    EntitySummary,
    EvidenceResult,
    ModelSummary,
)


class EntityNotFoundError(LookupError):
    """Raised when an entity cannot be found within the requested model."""


class ConceptNotFoundError(LookupError):
    """Raised when an entity has no assignment for the requested concept."""


class SemanticCatalog:
    """Read-only interface for querying a SemGEM SQLite catalog."""

    ENTITY_TYPES = frozenset({"reaction", "metabolite", "gene"})

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        if not self.db_path.is_file():
            raise FileNotFoundError(f"Semantic catalog not found: {self.db_path}")

        uri = f"{self.db_path.resolve().as_uri()}?mode=ro"
        self.conn = sqlite3.connect(uri, uri=True)
        self.conn.row_factory = sqlite3.Row

    def list_models(self) -> list[ModelSummary]:
        rows = self.conn.execute(
            """
            SELECT id, original_id, name, source_file, content_hash
            FROM models
            ORDER BY original_id
            """
        ).fetchall()
        return [
            ModelSummary(
                internal_id=row["id"],
                original_id=row["original_id"],
                name=row["name"],
                source_file=row["source_file"],
                content_hash=row["content_hash"],
            )
            for row in rows
        ]

    def get_entity(
        self,
        model_id: str,
        entity_type: str,
        entity_id: str,
    ) -> EntitySummary:
        row = self._entity_row(model_id, entity_type, entity_id)
        return EntitySummary(
            internal_id=row["internal_id"],
            model_id=row["model_id"],
            entity_type=row["entity_type"],
            original_id=row["original_id"],
            name=row["name"],
        )

    def get_annotations(
        self,
        model_id: str,
        entity_type: str,
        entity_id: str,
    ) -> list[AnnotationResult]:
        entity = self._entity_row(model_id, entity_type, entity_id)
        rows = self.conn.execute(
            """
            SELECT source, identifier
            FROM annotations
            WHERE entity_id = ?
            ORDER BY source, identifier
            """,
            (entity["internal_id"],),
        ).fetchall()
        return [
            AnnotationResult(source=row["source"], identifier=row["identifier"])
            for row in rows
        ]

    def get_concepts(
        self,
        model_id: str,
        entity_type: str,
        entity_id: str,
    ) -> list[ConceptSummary]:
        entity = self._entity_row(model_id, entity_type, entity_id)
        rows = self.conn.execute(
            """
            SELECT concept_name, confidence
            FROM semantic_concepts
            WHERE entity_id = ?
            ORDER BY concept_name
            """,
            (entity["internal_id"],),
        ).fetchall()
        return [
            ConceptSummary(name=row["concept_name"], confidence=row["confidence"])
            for row in rows
        ]

    def explain_concept(
        self,
        model_id: str,
        entity_type: str,
        entity_id: str,
        concept_name: str,
    ) -> ConceptExplanation:
        entity = self._entity_row(model_id, entity_type, entity_id)
        concept = self.conn.execute(
            """
            SELECT id, concept_name, confidence
            FROM semantic_concepts
            WHERE entity_id = ? AND concept_name = ?
            """,
            (entity["internal_id"], concept_name),
        ).fetchone()
        if concept is None:
            raise ConceptNotFoundError(
                f"Concept '{concept_name}' is not assigned to "
                f"{model_id}/{entity_type}/{entity_id}."
            )

        evidence_rows = self.conn.execute(
            """
            SELECT evidence_type, target_field, matched_value,
                   evidence_text, weight
            FROM concept_evidence
            WHERE concept_id = ?
            ORDER BY id
            """,
            (concept["id"],),
        ).fetchall()
        evidence = tuple(
            EvidenceResult(
                evidence_type=row["evidence_type"],
                target_field=row["target_field"],
                matched_value=row["matched_value"],
                text=row["evidence_text"],
                weight=row["weight"],
            )
            for row in evidence_rows
        )
        return ConceptExplanation(
            name=concept["concept_name"],
            confidence=concept["confidence"],
            evidence=evidence,
        )

    def _entity_row(
        self,
        model_id: str,
        entity_type: str,
        entity_id: str,
    ) -> sqlite3.Row:
        if entity_type not in self.ENTITY_TYPES:
            allowed = ", ".join(sorted(self.ENTITY_TYPES))
            raise ValueError(f"Unknown entity type '{entity_type}'. Expected: {allowed}.")

        row = self.conn.execute(
            """
            SELECT e.id AS internal_id,
                   m.original_id AS model_id,
                   e.entity_type,
                   e.original_id,
                   e.name
            FROM entities AS e
            JOIN models AS m ON m.id = e.model_id
            WHERE m.original_id = ?
              AND e.entity_type = ?
              AND e.original_id = ?
            """,
            (model_id, entity_type, entity_id),
        ).fetchone()
        if row is None:
            raise EntityNotFoundError(
                f"Entity not found: {model_id}/{entity_type}/{entity_id}."
            )
        return row

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
