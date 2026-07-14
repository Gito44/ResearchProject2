import json
import sqlite3
import warnings
from pathlib import Path
from typing import Any, Iterable


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
            columns = {
                row[1] for row in self.conn.execute("PRAGMA table_info(models)")
            }
            required_columns = {
                "id",
                "original_id",
                "name",
                "source_file",
                "content_hash",
            }
            if not required_columns <= columns:
                raise IncompatibleSchemaError(
                    "The existing database uses an older SemGEM schema. "
                    "Create a new catalog and rebuild it from the source model files."
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
        concepts: list,
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
                self._insert_semantic_concepts(
                    concepts,
                    entity_ids={
                        "reaction": reaction_ids,
                        "metabolite": metabolite_ids,
                        "gene": gene_ids,
                    },
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
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO models (original_id, name, source_file, content_hash)
            VALUES (?, ?, ?, ?)
            """,
            (original_id, name, source_file, content_hash),
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
                INSERT INTO metabolites (entity_id, compartment, formula, charge)
                VALUES (?, ?, ?, ?)
                """,
                (
                    entity_id,
                    metabolite.compartment,
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

    def _insert_semantic_concepts(
        self,
        concepts: list,
        entity_ids: dict[str, dict[str, int]],
    ) -> None:
        for concept in concepts:
            entity_id = entity_ids[concept.entity_type][concept.entity_id]
            cursor = self.conn.execute(
                """
                INSERT INTO semantic_concepts (
                    entity_id,
                    concept_name,
                    confidence
                )
                VALUES (?, ?, ?)
                """,
                (entity_id, concept.concept_name, concept.confidence),
            )
            concept_id = cursor.lastrowid

            for evidence in concept.evidence:
                self.conn.execute(
                    """
                    INSERT INTO concept_evidence (
                        concept_id,
                        evidence_type,
                        target_field,
                        matched_value,
                        evidence_text,
                        weight
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        concept_id,
                        evidence.evidence_type,
                        evidence.target_field,
                        evidence.matched_value,
                        evidence.evidence_text,
                        evidence.weight,
                    ),
                )

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
