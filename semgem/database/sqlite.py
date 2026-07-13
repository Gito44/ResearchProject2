import sqlite3
import json
from pathlib import Path


class SemanticDatabase:
    def __init__(self, db_path: str, schema_path: Path | str):
        self.db_path = Path(db_path)
        self.schema_path = Path(schema_path)
        self.conn = sqlite3.connect(self.db_path)

    def connect(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)

    def initialise(self):
        if self.conn is None:
            self.connect()

        with open(self.schema_path, "r") as f:
            self.conn.executescript(f.read())



    def insert_model(self, model, source_file: str):
        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT INTO models (model_id, model_name, source_file)
            VALUES (?, ?, ?)
            """,
            (model.id, model.name, source_file)
        )

        self.conn.commit()
        return cursor.lastrowid


    def insert_reactions(self, model_db_id: int, reactions: list):
        cursor = self.conn.cursor()

        for reaction in reactions:
            cursor.execute(
                """
                INSERT INTO reactions (
                    model_id,
                    reaction_id,
                    name,
                    lower_bound,
                    upper_bound,
                    objective_coefficient,
                    subsystem,
                    gene_reaction_rule,
                    equation
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    model_db_id,
                    reaction.reaction_id,
                    reaction.name,
                    reaction.lower_bound,
                    reaction.upper_bound,
                    reaction.objective_coefficient,
                    reaction.subsystem,
                    reaction.gene_reaction_rule,
                    reaction.equation,
                )
            )

            self._insert_annotations("reaction", reaction.reaction_id, reaction.annotations)

        self.conn.commit()


    def insert_metabolites(self, model_db_id: int, metabolites: list):
        cursor = self.conn.cursor()

        for metabolite in metabolites:
            cursor.execute(
                """
                INSERT INTO metabolites (
                    model_id,
                    metabolite_id,
                    name,
                    compartment,
                    formula,
                    charge
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    model_db_id,
                    metabolite.metabolite_id,
                    metabolite.name,
                    metabolite.compartment,
                    metabolite.formula,
                    metabolite.charge,
                )
            )

            self._insert_annotations("metabolite", metabolite.metabolite_id, metabolite.annotations)

        self.conn.commit()


    def insert_reaction_metabolites(self, rows: list):
        cursor = self.conn.cursor()

        for row in rows:
            cursor.execute(
                """
                INSERT INTO reaction_metabolites (
                    reaction_id,
                    metabolite_id,
                    coefficient
                )
                VALUES (?, ?, ?)
                """,
                (
                    row.reaction_id,
                    row.metabolite_id,
                    row.coefficient,
                )
            )

        self.conn.commit()

    def _insert_annotations(self, entity_type: str, entity_id: str, annotations: dict):
        cursor = self.conn.cursor()

        for key, value in annotations.items():
            cursor.execute(
                """
                INSERT INTO annotations (model_entity_type,
                                         model_entity_id,
                                         annotation_key,
                                         annotation_value)
                VALUES (?, ?, ?, ?)
                """,
                (
                    entity_type,
                    entity_id,
                    key,
                    json.dumps(value),
                ),
            )

    def insert_semantic_concepts(self, model_db_id: int, concepts):
        cursor = self.conn.cursor()

        for concept in concepts:
            cursor.execute(
                """
                INSERT INTO semantic_concepts (model_id,
                                               concept_name,
                                               entity_type,
                                               entity_id,
                                               confidence)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    model_db_id,
                    concept.concept_name,
                    concept.entity_type,
                    concept.entity_id,
                    concept.confidence,
                ),
            )

            concept_id = cursor.lastrowid

            for evidence in concept.evidence:
                cursor.execute(
                    """
                    INSERT INTO concept_evidence (concept_id,
                                                  evidence_type,
                                                  evidence_text,
                                                  weight)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        concept_id,
                        evidence.evidence_type,
                        evidence.evidence_text,
                        evidence.weight,
                    ),
                )

        self.conn.commit()

    def close(self):
        if self.conn is not None:
            self.conn.close()