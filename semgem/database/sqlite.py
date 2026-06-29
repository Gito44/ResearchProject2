import sqlite3
import json
from pathlib import Path

def initialise_database(db_path: str, schema_path: str):
    db_path = Path(db_path)
    schema_path = Path(schema_path)

    conn = sqlite3.connect(db_path)

    with open(schema_path, "r") as f:
        conn.executescript(f.read())

    return conn


def insert_model(conn, model, source_file: str):
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO models (model_id, model_name, source_file)
        VALUES (?, ?, ?)
        """,
        (model.id, model.name, source_file)
    )

    conn.commit()
    return cursor.lastrowid


def insert_reactions(conn, model_db_id: int, reactions: list):
    cursor = conn.cursor()

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
                reaction["reaction_id"],
                reaction["name"],
                reaction["lower_bound"],
                reaction["upper_bound"],
                reaction["objective_coefficient"],
                reaction["subsystem"],
                reaction["gene_reaction_rule"],
                reaction["equation"],
            )
        )

        for key, value in reaction["annotations"].items():
            cursor.execute(
                """
                INSERT INTO annotations (
                    model_entity_type,
                    model_entity_id,
                    annotation_key,
                    annotation_value
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    "reaction",
                    reaction["reaction_id"],
                    key,
                    json.dumps(value)
                )
            )

    conn.commit()


def insert_metabolites(conn, model_db_id: int, metabolites: list):
    cursor = conn.cursor()

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
                metabolite["metabolite_id"],
                metabolite["name"],
                metabolite["compartment"],
                metabolite["formula"],
                metabolite["charge"],
            )
        )

        for key, value in metabolite["annotations"].items():
            cursor.execute(
                """
                INSERT INTO annotations (
                    model_entity_type,
                    model_entity_id,
                    annotation_key,
                    annotation_value
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    "metabolite",
                    metabolite["metabolite_id"],
                    key,
                    json.dumps(value)
                )
            )

    conn.commit()


def insert_reaction_metabolites(conn, rows: list):
    cursor = conn.cursor()

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
                row["reaction_id"],
                row["metabolite_id"],
                row["coefficient"]
            )
        )

    conn.commit()