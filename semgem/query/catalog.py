import sqlite3
from pathlib import Path

from semgem.query.records import (
    AnnotationResult,
    CatalogStatistics,
    ConceptAssignment,
    ConceptExplanation,
    ConceptSummary,
    CoverageSummary,
    EntitySummary,
    EvidenceResult,
    ModelSummary,
    ProviderRunResult,
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

    def statistics(self, model_id: str | None = None) -> CatalogStatistics:
        """Return basic catalog or model-scoped entity and assignment totals."""
        if model_id is not None:
            self._require_model(model_id)
        condition = "" if model_id is None else "WHERE m.original_id = ?"
        parameters = () if model_id is None else (model_id,)
        counts = {
            row[0]: row[1]
            for row in self.conn.execute(
                f"""
                SELECT e.entity_type, COUNT(*)
                FROM entities AS e
                JOIN models AS m ON m.id = e.model_id
                {condition}
                GROUP BY e.entity_type
                """,
                parameters,
            )
        }
        assignment_count = self.conn.execute(
            f"""
            SELECT COUNT(*)
            FROM semantic_concepts AS c
            JOIN entities AS e ON e.id = c.entity_id
            JOIN models AS m ON m.id = e.model_id
            {condition}
            """,
            parameters,
        ).fetchone()[0]
        model_count = self.conn.execute(
            "SELECT COUNT(*) FROM models"
            if model_id is None
            else "SELECT COUNT(*) FROM models WHERE original_id = ?",
            parameters,
        ).fetchone()[0]
        return CatalogStatistics(
            model_count=model_count,
            reaction_count=counts.get("reaction", 0),
            metabolite_count=counts.get("metabolite", 0),
            gene_count=counts.get("gene", 0),
            semantic_assignment_count=assignment_count,
        )

    def coverage(self, model_id: str | None = None) -> CoverageSummary:
        """Return mutually interpretable reaction-level semantic coverage."""
        if model_id is not None:
            self._require_model(model_id)
        condition = "" if model_id is None else "AND m.original_id = ?"
        parameters = () if model_id is None else (model_id,)
        row = self.conn.execute(
            f"""
            WITH reaction_flags AS (
                SELECT e.id,
                       MAX(CASE WHEN c.concept_name LIKE 'pathway:%'
                                THEN 1 ELSE 0 END) AS pathway,
                       MAX(CASE
                           WHEN c.concept_name LIKE 'pathway:%'
                             OR c.concept_name LIKE 'objective:%'
                             OR c.concept_name LIKE 'exchange:%'
                             OR c.concept_name LIKE 'transport:%'
                             OR (
                                 c.concept_name LIKE 'reaction_type:%'
                                 AND c.concept_name <>
                                     'reaction_type:biochemical_reaction'
                             )
                           THEN 1 ELSE 0 END) AS actionable,
                       MAX(CASE WHEN c.id IS NOT NULL THEN 1 ELSE 0 END) AS covered
                FROM entities AS e
                JOIN models AS m ON m.id = e.model_id
                LEFT JOIN semantic_concepts AS c ON c.entity_id = e.id
                WHERE e.entity_type = 'reaction' {condition}
                GROUP BY e.id
            )
            SELECT COUNT(*) AS total,
                   SUM(pathway) AS pathway,
                   SUM(CASE WHEN actionable = 1 AND pathway = 0
                            THEN 1 ELSE 0 END) AS actionable_non_pathway,
                   SUM(actionable) AS actionable,
                   SUM(CASE WHEN covered = 1 AND actionable = 0
                            THEN 1 ELSE 0 END) AS generic_only,
                   SUM(CASE WHEN covered = 0 THEN 1 ELSE 0 END) AS unclassified
            FROM reaction_flags
            """,
            parameters,
        ).fetchone()
        return CoverageSummary(
            model_id=model_id,
            total_reactions=row["total"] or 0,
            pathway_reactions=row["pathway"] or 0,
            actionable_non_pathway_reactions=row["actionable_non_pathway"] or 0,
            actionable_reactions=row["actionable"] or 0,
            generic_only_reactions=row["generic_only"] or 0,
            unclassified_reactions=row["unclassified"] or 0,
        )

    def get_concept_assignments(
        self,
        concept_name: str,
        model_id: str | None = None,
        minimum_confidence: float = 0.0,
        limit: int = 100,
    ) -> list[ConceptAssignment]:
        """Return entities assigned to one canonical concept."""
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError("Minimum confidence must be between 0 and 1.")
        if limit < 1:
            raise ValueError("Search limit must be at least 1.")
        if model_id is not None:
            self._require_model(model_id)
        model_condition = "" if model_id is None else "AND m.original_id = ?"
        parameters = [concept_name, minimum_confidence]
        if model_id is not None:
            parameters.append(model_id)
        parameters.append(limit)
        rows = self.conn.execute(
            f"""
            SELECT e.id AS internal_id, m.original_id AS model_id,
                   e.entity_type, e.original_id, e.name,
                   c.concept_name, c.preferred_label, c.confidence
            FROM semantic_concepts AS c
            JOIN entities AS e ON e.id = c.entity_id
            JOIN models AS m ON m.id = e.model_id
            WHERE c.concept_name = ? AND c.confidence >= ? {model_condition}
            ORDER BY m.original_id, e.entity_type, e.original_id
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        return [
            ConceptAssignment(
                entity=EntitySummary(
                    internal_id=row["internal_id"],
                    model_id=row["model_id"],
                    entity_type=row["entity_type"],
                    original_id=row["original_id"],
                    name=row["name"],
                ),
                concept=ConceptSummary(
                    name=row["concept_name"],
                    preferred_label=row["preferred_label"],
                    confidence=row["confidence"],
                ),
            )
            for row in rows
        ]

    def list_unclassified_reactions(
        self,
        model_id: str | None = None,
        limit: int = 100,
    ) -> list[EntitySummary]:
        """Return reactions with no accepted semantic concept."""
        if limit < 1:
            raise ValueError("Search limit must be at least 1.")
        if model_id is not None:
            self._require_model(model_id)
        condition = "" if model_id is None else "AND m.original_id = ?"
        parameters = [] if model_id is None else [model_id]
        parameters.append(limit)
        rows = self.conn.execute(
            f"""
            SELECT e.id AS internal_id, m.original_id AS model_id,
                   e.entity_type, e.original_id, e.name
            FROM entities AS e
            JOIN models AS m ON m.id = e.model_id
            LEFT JOIN semantic_concepts AS c ON c.entity_id = e.id
            WHERE e.entity_type = 'reaction' {condition}
            GROUP BY e.id
            HAVING COUNT(c.id) = 0
            ORDER BY m.original_id, e.original_id
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        return [
            EntitySummary(
                internal_id=row["internal_id"],
                model_id=row["model_id"],
                entity_type=row["entity_type"],
                original_id=row["original_id"],
                name=row["name"],
            )
            for row in rows
        ]

    def list_provider_runs(self) -> list[ProviderRunResult]:
        """Return provider executions and their resolution summaries."""
        if self.conn.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'enrichment_runs'
            """
        ).fetchone() is None:
            return []
        rows = self.conn.execute(
            """
            SELECT provider, status, resource_version, requested_count,
                   resolved_count, unresolved_count, started_at,
                   completed_at, error_summary
            FROM enrichment_runs
            ORDER BY id
            """
        ).fetchall()
        return [
            ProviderRunResult(
                provider=row["provider"],
                status=row["status"],
                resource_version=row["resource_version"],
                requested=row["requested_count"],
                resolved=row["resolved_count"],
                unresolved=row["unresolved_count"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                error_summary=row["error_summary"],
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

    def _require_model(self, model_id: str) -> None:
        if self.conn.execute(
            "SELECT 1 FROM models WHERE original_id = ?", (model_id,)
        ).fetchone() is None:
            raise EntityNotFoundError(f"Model not found: {model_id}.")

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
