import sqlite3
from pathlib import Path

from semgem.query.records import (
    AnnotationResult,
    ConceptExplanation,
    ConceptSummary,
    EntitySummary,
    EvidenceResult,
    ModelSummary,
    SearchMatch,
    SearchResult,
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

    def search(
        self,
        query: str,
        model_id: str | None = None,
        entity_type: str | None = None,
        annotation_source: str | None = None,
        limit: int = 100,
    ) -> list[SearchResult]:
        """Search entity IDs, names, annotations, and semantic concepts."""
        query = query.strip()
        if not query:
            raise ValueError("Search query must not be empty.")
        if entity_type is not None and entity_type not in self.ENTITY_TYPES:
            allowed = ", ".join(sorted(self.ENTITY_TYPES))
            raise ValueError(f"Unknown entity type '{entity_type}'. Expected: {allowed}.")
        if limit < 1:
            raise ValueError("Search limit must be at least 1.")

        scope_conditions = []
        scope_parameters: list[str] = []
        if model_id is not None:
            scope_conditions.append("m.original_id = ?")
            scope_parameters.append(model_id)
        if entity_type is not None:
            scope_conditions.append("e.entity_type = ?")
            scope_parameters.append(entity_type)

        scope_where = ""
        if scope_conditions:
            scope_where = "WHERE " + " AND ".join(scope_conditions)

        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped.lower()}%"

        match_queries = []
        match_parameters: list[str] = []
        if annotation_source is None:
            match_queries.extend(
                [
                    """
                    SELECT internal_id, 'id' AS match_field, NULL AS match_source,
                           original_id AS matched_value
                    FROM scoped
                    WHERE LOWER(original_id) LIKE ? ESCAPE '\\'
                    """,
                    """
                    SELECT internal_id, 'name' AS match_field, NULL AS match_source,
                           name AS matched_value
                    FROM scoped
                    WHERE name IS NOT NULL
                      AND LOWER(name) LIKE ? ESCAPE '\\'
                    """,
                    """
                    SELECT s.internal_id, 'annotation' AS match_field,
                           a.source AS match_source, a.identifier AS matched_value
                    FROM scoped AS s
                    JOIN annotations AS a ON a.entity_id = s.internal_id
                    WHERE LOWER(a.identifier) LIKE ? ESCAPE '\\'
                    """,
                    """
                    SELECT s.internal_id, 'concept' AS match_field,
                           NULL AS match_source,
                           c.concept_name || ' (' || c.preferred_label || ')'
                               AS matched_value
                    FROM scoped AS s
                    JOIN semantic_concepts AS c ON c.entity_id = s.internal_id
                    WHERE LOWER(c.concept_name) LIKE ? ESCAPE '\\'
                       OR LOWER(c.preferred_label) LIKE ? ESCAPE '\\'
                    """,
                ]
            )
            match_parameters.extend([pattern, pattern, pattern, pattern, pattern])
        else:
            match_queries.append(
                """
                SELECT s.internal_id, 'annotation' AS match_field,
                       a.source AS match_source, a.identifier AS matched_value
                FROM scoped AS s
                JOIN annotations AS a ON a.entity_id = s.internal_id
                WHERE a.source = ?
                  AND LOWER(a.identifier) LIKE ? ESCAPE '\\'
                """
            )
            match_parameters.extend([annotation_source, pattern])

        match_sql = " UNION ALL ".join(match_queries)
        rows = self.conn.execute(
            f"""
            WITH scoped AS (
                SELECT e.id AS internal_id,
                       m.original_id AS model_id,
                       e.entity_type,
                       e.original_id,
                       e.name
                FROM entities AS e
                JOIN models AS m ON m.id = e.model_id
                {scope_where}
            ),
            match_data AS (
                {match_sql}
            ),
            selected_entities AS (
                SELECT s.internal_id
                FROM scoped AS s
                JOIN match_data AS md ON md.internal_id = s.internal_id
                GROUP BY s.internal_id
                ORDER BY s.model_id, s.entity_type, s.original_id
                LIMIT ?
            )
            SELECT s.internal_id, s.model_id, s.entity_type, s.original_id, s.name,
                   md.match_field, md.match_source, md.matched_value
            FROM selected_entities AS selected
            JOIN scoped AS s ON s.internal_id = selected.internal_id
            JOIN match_data AS md ON md.internal_id = selected.internal_id
            ORDER BY s.model_id, s.entity_type, s.original_id,
                     md.match_field, md.match_source, md.matched_value
            """,
            [*scope_parameters, *match_parameters, limit],
        ).fetchall()

        grouped: dict[int, SearchResult] = {}
        for row in rows:
            match = SearchMatch(
                field=row["match_field"],
                source=row["match_source"],
                value=row["matched_value"],
            )
            if row["internal_id"] not in grouped:
                grouped[row["internal_id"]] = SearchResult(
                    entity=EntitySummary(
                        internal_id=row["internal_id"],
                        model_id=row["model_id"],
                        entity_type=row["entity_type"],
                        original_id=row["original_id"],
                        name=row["name"],
                    ),
                    matches=(match,),
                )
            else:
                result = grouped[row["internal_id"]]
                grouped[row["internal_id"]] = SearchResult(
                    entity=result.entity,
                    matches=(*result.matches, match),
                )
        return list(grouped.values())

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
            SELECT concept_name, preferred_label, confidence
            FROM semantic_concepts
            WHERE entity_id = ?
            ORDER BY concept_name
            """,
            (entity["internal_id"],),
        ).fetchall()
        return [
            ConceptSummary(
                name=row["concept_name"],
                preferred_label=row["preferred_label"],
                confidence=row["confidence"],
            )
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
            SELECT id, concept_name, preferred_label, confidence
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
            SELECT evidence_code, source, observed_value,
                   explanation, weight, annotation_id,
                   assertion_id, relationship_id
            FROM concept_evidence
            WHERE concept_id = ?
            ORDER BY id
            """,
            (concept["id"],),
        ).fetchall()
        evidence = tuple(
            EvidenceResult(
                evidence_code=row["evidence_code"],
                source=row["source"],
                observed_value=row["observed_value"],
                explanation=row["explanation"],
                weight=row["weight"],
                annotation_id=row["annotation_id"],
                assertion_id=row["assertion_id"],
                relationship_id=row["relationship_id"],
            )
            for row in evidence_rows
        )
        return ConceptExplanation(
            name=concept["concept_name"],
            preferred_label=concept["preferred_label"],
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
