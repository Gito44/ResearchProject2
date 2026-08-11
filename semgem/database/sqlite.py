import json
import sqlite3
import warnings
from pathlib import Path
from typing import Any, Iterable

from semgem.core.records import (
    AnnotationInputRecord,
    EnrichmentAssertionRecord,
    ExternalTermRecord,
    ExternalTermRelationshipRecord,
    ProviderRelationshipEvidenceRecord,
)
from semgem.evidence.rules import ScoredConcept


class DuplicateModelError(ValueError):
    """Raised when the same model ID and file content are already stored."""


class ModelIdentityConflictError(ValueError):
    """Raised when an existing model ID is imported with different content."""


class EntityTypeError(ValueError):
    """Raised when a type-specific row references the wrong entity type."""


class IncompatibleSchemaError(ValueError):
    """Raised when an existing database uses an unsupported older schema."""


class SemanticDatabase:
    def __init__(self, db_path: str | Path, schema_path: str | Path):
        self.db_path = Path(db_path)
        self.schema_path = Path(schema_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA foreign_keys = ON")

    def initialise(self) -> None:
        existing_models_table = self.conn.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'models'
            """
        ).fetchone()
        if existing_models_table is not None:
            schema_version = self.conn.execute("PRAGMA user_version").fetchone()[0]
            if schema_version != 5:
                raise IncompatibleSchemaError(
                    f"The existing database uses SemGEM schema version "
                    f"{schema_version}; version 5 is required. Create a new "
                    "catalog and rebuild it from the source model files."
                )
            columns = {
                row[1] for row in self.conn.execute("PRAGMA table_info(models)")
            }
            required_columns = {
                "id",
                "original_id",
                "name",
                "source_file",
                "content_hash",
                "compartments_json",
            }
            if not required_columns <= columns:
                raise IncompatibleSchemaError(
                    "The existing database uses an older SemGEM schema. "
                    "Create a new catalog and rebuild it from the source model files."
                )
            concept_columns = {
                row[1]
                for row in self.conn.execute(
                    "PRAGMA table_info(semantic_concepts)"
                )
            }
            if "preferred_label" not in concept_columns:
                raise IncompatibleSchemaError(
                    "The existing database is missing v0.5 semantic-label "
                    "fields. Create a new catalog and rebuild it from the "
                    "source model files."
                )

        with self.schema_path.open("r", encoding="utf-8") as schema_file:
            self.conn.executescript(schema_file.read())

    def import_model(
        self,
        model,
        source_file: str,
        content_hash: str,
        reactions: list,
        metabolites: list,
        genes: list,
        stoichiometry: list,
        reaction_genes: list,
    ) -> int:
        """Import one complete model in a single transaction."""
        original_id = str(model.id or "").strip()
        if not original_id:
            raise ValueError("The model must have a non-empty SBML model ID.")

        try:
            with self.conn:
                self._validate_model_identity(original_id, content_hash)
                model_db_id = self._insert_model(
                    original_id=original_id,
                    name=model.name,
                    source_file=source_file,
                    content_hash=content_hash,
                    compartments=dict(model.compartments),
                )

                reaction_ids = self._insert_reactions(model_db_id, reactions)
                metabolite_ids = self._insert_metabolites(model_db_id, metabolites)
                gene_ids = self._insert_genes(model_db_id, genes)

                self._insert_stoichiometry(
                    stoichiometry,
                    reaction_ids=reaction_ids,
                    metabolite_ids=metabolite_ids,
                )
                self._insert_reaction_genes(
                    reaction_genes,
                    reaction_ids=reaction_ids,
                    gene_ids=gene_ids,
                )
                return model_db_id
        except Exception:
            self.conn.rollback()
            raise

    def _validate_model_identity(self, original_id: str, content_hash: str) -> None:
        existing = self.conn.execute(
            "SELECT content_hash FROM models WHERE original_id = ?",
            (original_id,),
        ).fetchone()

        if existing is not None:
            if existing[0] == content_hash:
                raise DuplicateModelError(
                    f"Model '{original_id}' with identical content is already imported."
                )
            raise ModelIdentityConflictError(
                f"Model ID '{original_id}' already exists with different content."
            )

        duplicate_content = self.conn.execute(
            "SELECT original_id FROM models WHERE content_hash = ? LIMIT 1",
            (content_hash,),
        ).fetchone()
        if duplicate_content is not None:
            warnings.warn(
                f"Model content is identical to existing model "
                f"'{duplicate_content[0]}', but the model ID differs.",
                UserWarning,
                stacklevel=2,
            )

    def _insert_model(
        self,
        original_id: str,
        name: str | None,
        source_file: str,
        content_hash: str,
        compartments: dict[str, str],
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO models (
                original_id,
                name,
                source_file,
                content_hash,
                compartments_json
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                original_id,
                name,
                source_file,
                content_hash,
                json.dumps(compartments, sort_keys=True),
            ),
        )
        return cursor.lastrowid

    def _insert_entity(
        self,
        model_db_id: int,
        entity_type: str,
        original_id: str,
        name: str | None,
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO entities (model_id, entity_type, original_id, name)
            VALUES (?, ?, ?, ?)
            """,
            (model_db_id, entity_type, original_id, name),
        )
        return cursor.lastrowid

    def _assert_entity_type(self, entity_id: int, expected_type: str) -> None:
        row = self.conn.execute(
            "SELECT entity_type FROM entities WHERE id = ?",
            (entity_id,),
        ).fetchone()
        if row is None:
            raise EntityTypeError(f"Entity {entity_id} does not exist.")
        if row[0] != expected_type:
            raise EntityTypeError(
                f"Entity {entity_id} has type '{row[0]}', not '{expected_type}'."
            )

    def _insert_reactions(self, model_db_id: int, reactions: list) -> dict[str, int]:
        entity_ids = {}
        for reaction in reactions:
            entity_id = self._insert_entity(
                model_db_id,
                "reaction",
                reaction.reaction_id,
                reaction.name,
            )
            self._assert_entity_type(entity_id, "reaction")
            self.conn.execute(
                """
                INSERT INTO reactions (
                    entity_id,
                    lower_bound,
                    upper_bound,
                    objective_coefficient,
                    subsystem,
                    gene_reaction_rule,
                    equation
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    reaction.lower_bound,
                    reaction.upper_bound,
                    reaction.objective_coefficient,
                    reaction.subsystem,
                    reaction.gene_reaction_rule,
                    reaction.equation,
                ),
            )
            self._insert_annotations(entity_id, reaction.annotations)
            entity_ids[reaction.reaction_id] = entity_id
        return entity_ids

    def _insert_metabolites(
        self, model_db_id: int, metabolites: list
    ) -> dict[str, int]:
        entity_ids = {}
        for metabolite in metabolites:
            entity_id = self._insert_entity(
                model_db_id,
                "metabolite",
                metabolite.metabolite_id,
                metabolite.name,
            )
            self._assert_entity_type(entity_id, "metabolite")
            self.conn.execute(
                """
                INSERT INTO metabolites (
                    entity_id,
                    compartment,
                    compartment_free_id,
                    normalized_name,
                    formula,
                    charge
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    metabolite.compartment,
                    metabolite.compartment_free_id,
                    metabolite.normalized_name,
                    metabolite.formula,
                    metabolite.charge,
                ),
            )
            self._insert_annotations(entity_id, metabolite.annotations)
            entity_ids[metabolite.metabolite_id] = entity_id
        return entity_ids

    def _insert_genes(self, model_db_id: int, genes: list) -> dict[str, int]:
        entity_ids = {}
        for gene in genes:
            entity_id = self._insert_entity(
                model_db_id,
                "gene",
                gene.gene_id,
                gene.name,
            )
            self._assert_entity_type(entity_id, "gene")
            self.conn.execute(
                "INSERT INTO genes (entity_id) VALUES (?)",
                (entity_id,),
            )
            self._insert_annotations(entity_id, gene.annotations)
            entity_ids[gene.gene_id] = entity_id
        return entity_ids

    def _insert_stoichiometry(
        self,
        rows: list,
        reaction_ids: dict[str, int],
        metabolite_ids: dict[str, int],
    ) -> None:
        for row in rows:
            self.conn.execute(
                """
                INSERT INTO reaction_metabolites (
                    reaction_entity_id,
                    metabolite_entity_id,
                    coefficient
                )
                VALUES (?, ?, ?)
                """,
                (
                    reaction_ids[row.reaction_id],
                    metabolite_ids[row.metabolite_id],
                    row.coefficient,
                ),
            )

    def _insert_reaction_genes(
        self,
        rows: list,
        reaction_ids: dict[str, int],
        gene_ids: dict[str, int],
    ) -> None:
        for row in rows:
            self.conn.execute(
                """
                INSERT INTO reaction_genes (reaction_entity_id, gene_entity_id)
                VALUES (?, ?)
                """,
                (reaction_ids[row.reaction_id], gene_ids[row.gene_id]),
            )

    def _insert_annotations(self, entity_id: int, annotations: dict) -> None:
        for source, raw_value in annotations.items():
            for identifier in self._annotation_values(raw_value):
                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO annotations (entity_id, source, identifier)
                    VALUES (?, ?, ?)
                    """,
                    (entity_id, str(source), identifier),
                )

    @staticmethod
    def _annotation_values(raw_value: Any) -> Iterable[str]:
        if isinstance(raw_value, (list, tuple, set)):
            for value in raw_value:
                yield str(value)
        elif isinstance(raw_value, dict):
            yield json.dumps(raw_value, sort_keys=True)
        elif raw_value is not None:
            yield str(raw_value)

    def store_enrichment(
        self,
        terms: Iterable[ExternalTermRecord],
        relationships: Iterable[ExternalTermRelationshipRecord],
        assertions: Iterable[EnrichmentAssertionRecord],
    ) -> None:
        """Store one provider's enrichment records atomically."""
        try:
            with self.conn:
                for term in terms:
                    self._upsert_external_term(term)
                for relationship in relationships:
                    self._insert_external_term_relationship(relationship)
                for assertion in assertions:
                    self._insert_enrichment_assertion(assertion)
        except Exception:
            self.conn.rollback()
            raise

    def _upsert_external_term(self, term: ExternalTermRecord) -> int:
        self.conn.execute(
            """
            INSERT INTO external_terms (
                source,
                identifier,
                term_type,
                name,
                description,
                source_version,
                is_obsolete
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (source, identifier) DO UPDATE SET
                term_type = excluded.term_type,
                name = COALESCE(excluded.name, external_terms.name),
                description = COALESCE(
                    excluded.description,
                    external_terms.description
                ),
                source_version = COALESCE(
                    excluded.source_version,
                    external_terms.source_version
                ),
                is_obsolete = excluded.is_obsolete
            """,
            (
                term.source,
                term.identifier,
                term.term_type,
                term.name,
                term.description,
                term.source_version,
                int(term.is_obsolete),
            ),
        )
        return self._external_term_id(term.source, term.identifier)

    def _external_term_id(self, source: str, identifier: str) -> int:
        row = self.conn.execute(
            """
            SELECT id
            FROM external_terms
            WHERE source = ? AND identifier = ?
            """,
            (source, identifier),
        ).fetchone()
        if row is None:
            raise ValueError(f"External term '{source}:{identifier}' is not stored.")
        return row[0]

    def _insert_external_term_relationship(
        self,
        relationship: ExternalTermRelationshipRecord,
    ) -> int:
        subject_id = self._external_term_id(
            relationship.subject_source,
            relationship.subject_identifier,
        )
        object_id = self._external_term_id(
            relationship.object_source,
            relationship.object_identifier,
        )
        self.conn.execute(
            """
            INSERT OR IGNORE INTO external_term_relationships (
                subject_term_id,
                predicate,
                object_term_id
            )
            VALUES (?, ?, ?)
            """,
            (subject_id, relationship.predicate, object_id),
        )
        relationship_id = self.conn.execute(
            """
            SELECT id
            FROM external_term_relationships
            WHERE subject_term_id = ?
              AND predicate = ?
              AND object_term_id = ?
            """,
            (subject_id, relationship.predicate, object_id),
        ).fetchone()[0]
        self._replace_provider_relationship_evidence(
            relationship_id,
            relationship.evidence,
        )
        return relationship_id

    def _replace_provider_relationship_evidence(
        self,
        relationship_id: int,
        evidence_records: Iterable[ProviderRelationshipEvidenceRecord],
    ) -> None:
        records = tuple(evidence_records)
        providers = {evidence.provider for evidence in records}
        for provider in providers:
            self.conn.execute(
                """
                DELETE FROM provider_relationship_evidence
                WHERE relationship_id = ? AND provider = ?
                """,
                (relationship_id, provider),
            )

        for evidence in records:
            self.conn.execute(
                """
                INSERT INTO provider_relationship_evidence (
                    relationship_id,
                    run_id,
                    provider,
                    retrieval_method,
                    source_identifier,
                    resource_version,
                    retrieved_at,
                    details
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    relationship_id,
                    evidence.run_id,
                    evidence.provider,
                    evidence.retrieval_method,
                    evidence.source_identifier,
                    evidence.resource_version,
                    evidence.retrieved_at,
                    evidence.details,
                ),
            )

    def _insert_enrichment_assertion(
        self,
        assertion: EnrichmentAssertionRecord,
    ) -> None:
        if self.conn.execute(
            "SELECT 1 FROM entities WHERE id = ?",
            (assertion.entity_id,),
        ).fetchone() is None:
            raise ValueError(f"Entity {assertion.entity_id} is not stored.")

        term_id = self._external_term_id(
            assertion.term_source,
            assertion.term_identifier,
        )
        self.conn.execute(
            """
            INSERT OR IGNORE INTO enrichment_assertions (
                entity_id,
                predicate,
                external_term_id
            )
            VALUES (?, ?, ?)
            """,
            (
                assertion.entity_id,
                assertion.predicate,
                term_id,
            ),
        )
        assertion_id = self.conn.execute(
            """
            SELECT id
            FROM enrichment_assertions
            WHERE entity_id = ?
              AND predicate = ?
              AND external_term_id = ?
            """,
            (
                assertion.entity_id,
                assertion.predicate,
                term_id,
            ),
        ).fetchone()[0]

        # Re-running a provider refreshes only that provider's provenance.
        # Evidence supplied by other providers must remain available for
        # corroboration and later scoring.
        providers = {evidence.provider for evidence in assertion.evidence}
        for provider in providers:
            self.conn.execute(
                """
                DELETE FROM entity_assertion_evidence
                WHERE assertion_id = ? AND provider = ?
                """,
                (assertion_id, provider),
            )
        for evidence in assertion.evidence:
            self.conn.execute(
                """
                INSERT INTO entity_assertion_evidence (
                    assertion_id,
                    relationship_id,
                    run_id,
                    provider,
                    evidence_type,
                    source_annotation_id,
                    source_identifier,
                    retrieval_method,
                    resource_version,
                    retrieved_at,
                    details
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    assertion_id,
                    evidence.relationship_id,
                    evidence.run_id,
                    evidence.provider,
                    evidence.evidence_type,
                    evidence.source_annotation_id,
                    evidence.source_identifier,
                    evidence.retrieval_method,
                    evidence.resource_version,
                    evidence.retrieved_at,
                    evidence.details,
                ),
            )

    def start_enrichment_run(
        self,
        provider: str,
        started_at: str,
        resource_version: str | None = None,
    ) -> int:
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO enrichment_runs (
                    provider,
                    status,
                    started_at,
                    resource_version
                )
                VALUES (?, 'running', ?, ?)
                """,
                (provider, started_at, resource_version),
            )
        return cursor.lastrowid

    def finish_enrichment_run(
        self,
        run_id: int,
        status: str,
        completed_at: str,
        requested_count: int,
        resolved_count: int,
        unresolved_count: int,
        error_summary: str | None = None,
    ) -> None:
        if status not in {"completed", "partial", "failed"}:
            raise ValueError(
                "Finished enrichment status must be completed, partial, or failed."
            )

        with self.conn:
            cursor = self.conn.execute(
                """
                UPDATE enrichment_runs
                SET status = ?,
                    completed_at = ?,
                    requested_count = ?,
                    resolved_count = ?,
                    unresolved_count = ?,
                    error_summary = ?
                WHERE id = ?
                """,
                (
                    status,
                    completed_at,
                    requested_count,
                    resolved_count,
                    unresolved_count,
                    error_summary,
                    run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"Enrichment run {run_id} does not exist.")

    def annotation_inputs(
        self,
        sources: Iterable[str] | None = None,
    ) -> list[AnnotationInputRecord]:
        parameters: list[str] = []
        where = ""
        if sources is not None:
            selected = sorted(set(sources))
            if not selected:
                return []
            placeholders = ", ".join("?" for _ in selected)
            where = f"WHERE source IN ({placeholders})"
            parameters.extend(selected)
        rows = self.conn.execute(
            f"""
            SELECT id, entity_id, source, identifier
            FROM annotations
            {where}
            ORDER BY source, identifier, entity_id
            """,
            parameters,
        ).fetchall()
        return [
            AnnotationInputRecord(
                annotation_id=row[0],
                entity_id=row[1],
                source=row[2],
                identifier=row[3],
            )
            for row in rows
        ]

    def external_identifiers(self, source: str) -> set[str]:
        return {
            row[0]
            for row in self.conn.execute(
                "SELECT identifier FROM external_terms WHERE source = ?",
                (source,),
            ).fetchall()
        }

    def external_identifiers_with_relationship(
        self,
        source: str,
        predicate: str,
    ) -> set[str]:
        return {
            row[0]
            for row in self.conn.execute(
                """
                SELECT DISTINCT subject.identifier
                FROM external_terms AS subject
                JOIN external_term_relationships AS relationship
                  ON relationship.subject_term_id = subject.id
                WHERE subject.source = ?
                  AND relationship.predicate = ?
                """,
                (source, predicate),
            ).fetchall()
        }

    def metabolite_standardization_rows(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT entity.id,
                   entity.model_id,
                   entity.original_id,
                   entity.name,
                   metabolite.compartment,
                   metabolite.compartment_free_id,
                   metabolite.normalized_name,
                   metabolite.formula,
                   metabolite.charge
            FROM metabolites AS metabolite
            JOIN entities AS entity ON entity.id = metabolite.entity_id
            ORDER BY entity.id
            """
        ).fetchall()
        return [
            {
                "entity_id": row[0],
                "model_id": row[1],
                "original_id": row[2],
                "name": row[3],
                "compartment": row[4],
                "compartment_free_id": row[5],
                "normalized_name": row[6],
                "formula": row[7],
                "charge": row[8],
            }
            for row in rows
        ]

    def reaction_stoichiometry_rows(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT reaction_entity.id,
                   reaction_entity.original_id,
                   metabolite_entity.id,
                   metabolite.compartment_free_id,
                   metabolite.compartment,
                   link.coefficient
            FROM reaction_metabolites AS link
            JOIN entities AS reaction_entity
              ON reaction_entity.id = link.reaction_entity_id
            JOIN metabolites AS metabolite
              ON metabolite.entity_id = link.metabolite_entity_id
            JOIN entities AS metabolite_entity
              ON metabolite_entity.id = link.metabolite_entity_id
            ORDER BY reaction_entity.id, metabolite_entity.id
            """
        ).fetchall()
        return [
            {
                "reaction_entity_id": row[0],
                "reaction_id": row[1],
                "metabolite_entity_id": row[2],
                "compartment_free_id": row[3],
                "compartment": row[4],
                "coefficient": float(row[5]),
            }
            for row in rows
        ]

    def evidence_entity_rows(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT e.id,
                   e.entity_type,
                   e.original_id,
                   e.name,
                   r.objective_coefficient,
                   r.equation,
                   r.subsystem,
                   e.model_id
            FROM entities AS e
            LEFT JOIN reactions AS r ON r.entity_id = e.id
            ORDER BY e.id
            """
        ).fetchall()
        compartment_maps = {
            row[0]: json.loads(row[1] or "{}")
            for row in self.conn.execute(
                "SELECT id, compartments_json FROM models"
            ).fetchall()
        }
        reaction_metabolites: dict[
            int,
            list[tuple[str, str, str, str, str, float]],
        ] = {}
        for row in self.conn.execute(
            """
            SELECT rm.reaction_entity_id,
                   entity.original_id,
                   entity.name,
                   metabolite.compartment,
                   metabolite.compartment_free_id,
                   metabolite.normalized_name,
                   rm.coefficient
            FROM reaction_metabolites AS rm
            JOIN metabolites AS metabolite
              ON metabolite.entity_id = rm.metabolite_entity_id
            JOIN entities AS entity
              ON entity.id = rm.metabolite_entity_id
            ORDER BY rm.reaction_entity_id, entity.original_id
            """
        ).fetchall():
            reaction_metabolites.setdefault(row[0], []).append(
                (
                    row[1] or "",
                    row[2] or "",
                    row[3] or "",
                    row[4] or "",
                    row[5] or "",
                    float(row[6]),
                )
            )
        output = []
        for row in rows:
            original_id = row[2] or ""
            name = row[3] or ""
            equation = row[5] or ""
            subsystem = row[6] or ""
            participants = reaction_metabolites.get(row[0], [])
            compartment_ids = sorted(
                {item[2] for item in participants if item[2]}
            )
            compartment_map = compartment_maps.get(row[7], {})
            compartment_names = [
                compartment_map.get(identifier, identifier)
                for identifier in compartment_ids
            ]

            def participant_text(items):
                return " ".join(
                    (
                        f"{metabolite_id} {metabolite_name} "
                        f"{compartment_free_id} {normalized_name}"
                    ).strip()
                    for (
                        metabolite_id,
                        metabolite_name,
                        _,
                        compartment_free_id,
                        normalized_name,
                        _,
                    ) in items
                )

            reactants = [item for item in participants if item[5] < 0]
            products = [item for item in participants if item[5] > 0]
            metabolite_text = participant_text(participants)
            reactant_text = participant_text(reactants)
            product_text = participant_text(products)
            is_multi_compartment = len(compartment_ids) > 1

            def compartment_free_id(
                metabolite_id: str,
                compartment: str,
            ) -> str | None:
                for suffix in (
                    f"_{compartment}",
                    f"[{compartment}]",
                    f"__{compartment}",
                ):
                    if metabolite_id.endswith(suffix):
                        return metabolite_id[: -len(suffix)]
                return None

            transported_reactants = {
                base
                for metabolite_id, _, compartment, _, _, _ in reactants
                if (
                    base := compartment_free_id(metabolite_id, compartment)
                )
            }
            transported_products = {
                base
                for metabolite_id, _, compartment, _, _, _ in products
                if (
                    base := compartment_free_id(metabolite_id, compartment)
                )
            }
            transported_metabolites = sorted(
                transported_reactants & transported_products
            )
            has_transport_signature = (
                is_multi_compartment and bool(transported_metabolites)
            )
            output.append(
                {
                    "entity_id": row[0],
                    "entity_type": row[1],
                    "original_id": original_id,
                    "name": name,
                    "objective_coefficient": row[4],
                    "equation": equation,
                    "subsystem": subsystem,
                    "metabolite_text": metabolite_text,
                    "reactant_text": reactant_text,
                    "product_text": product_text,
                    "compartment_ids": " ".join(compartment_ids),
                    "compartment_names": " ".join(compartment_names),
                    "is_multi_compartment": is_multi_compartment,
                    "has_transport_signature": has_transport_signature,
                    "transported_metabolites": " ".join(transported_metabolites),
                    "transport_compartment_names": (
                        " ".join(compartment_names)
                        if has_transport_signature
                        else ""
                    ),
                    "combined_text": " ".join(
                        (
                            original_id,
                            name,
                            equation,
                            metabolite_text,
                            subsystem,
                        )
                    ),
                }
            )
        return output

    def external_evidence_rows(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH RECURSIVE reachable (
                assertion_id,
                entity_id,
                term_id,
                distance,
                relationship_id,
                predicate
            ) AS (
                SELECT ea.id,
                       ea.entity_id,
                       ea.external_term_id,
                       0,
                       NULL,
                       ea.predicate
                FROM enrichment_assertions AS ea

                UNION ALL

                SELECT reachable.assertion_id,
                       reachable.entity_id,
                       rel.object_term_id,
                       reachable.distance + 1,
                       rel.id,
                       rel.predicate
                FROM reachable
                JOIN external_term_relationships AS rel
                  ON rel.subject_term_id = reachable.term_id
                WHERE reachable.distance < 20
            )
            SELECT DISTINCT
                   reachable.entity_id,
                   entity.entity_type,
                   reachable.assertion_id,
                   reachable.relationship_id,
                   reachable.distance,
                   reachable.predicate,
                   term.name,
                   evidence.provider,
                   evidence.source_annotation_id
            FROM reachable
            JOIN entities AS entity ON entity.id = reachable.entity_id
            JOIN external_terms AS term ON term.id = reachable.term_id
            JOIN entity_assertion_evidence AS evidence
              ON evidence.assertion_id = reachable.assertion_id
            WHERE term.name IS NOT NULL
            ORDER BY reachable.entity_id,
                     reachable.assertion_id,
                     reachable.distance,
                     term.name
            """
        ).fetchall()
        return [
            {
                "entity_id": row[0],
                "entity_type": row[1],
                "assertion_id": row[2],
                "relationship_id": row[3],
                "distance": row[4],
                "predicate": row[5],
                "term_name": row[6],
                "provider": row[7],
                "source_annotation_id": row[8],
            }
            for row in rows
        ]

    def replace_semantic_concepts(
        self,
        concepts: Iterable[ScoredConcept],
    ) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM semantic_concepts")
            for concept in concepts:
                cursor = self.conn.execute(
                    """
                    INSERT INTO semantic_concepts (
                        entity_id,
                        concept_name,
                        preferred_label,
                        confidence
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        concept.entity_id,
                        concept.concept_id,
                        concept.preferred_label,
                        concept.confidence,
                    ),
                )
                concept_db_id = cursor.lastrowid
                for evidence in concept.evidence:
                    candidate = evidence.candidate
                    self.conn.execute(
                        """
                        INSERT INTO concept_evidence (
                            concept_id,
                            evidence_code,
                            source,
                            explanation,
                            observed_value,
                            weight,
                            annotation_id,
                            assertion_id,
                            relationship_id
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            concept_db_id,
                            candidate.evidence_code,
                            candidate.source,
                            candidate.explanation,
                            candidate.observed_value,
                            evidence.weight,
                            candidate.annotation_id,
                            candidate.assertion_id,
                            candidate.relationship_id,
                        ),
                    )

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
