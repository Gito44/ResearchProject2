from pathlib import Path
import typer

from semgem.io.load_model import load_sbml_model
from semgem.extract.reactions import extract_reactions
from semgem.extract.metabolites import extract_metabolites
from semgem.extract.stoichiometry import extract_reaction_metabolites
from semgem.database.sqlite import (
    initialise_database,
    insert_model,
    insert_reactions,
    insert_metabolites,
    insert_reaction_metabolites,
)

app = typer.Typer()

@app.callback()
def main():
    """
    semgem command line interface.
    """
    pass

@app.command()
def build(
    model_path: str,
    out: str = "outputs/semantic_layer.sqlite"
):
    """
    Build a basic semantic layer SQLite database from an SBML model.
    """

    model = load_sbml_model(model_path)

    schema_path = Path(__file__).parent / "database" / "schema.sql"
    conn = initialise_database(out, schema_path)

    model_db_id = insert_model(conn, model, model_path)

    reactions = extract_reactions(model)
    metabolites = extract_metabolites(model)
    reaction_metabolites = extract_reaction_metabolites(model)

    insert_reactions(conn, model_db_id, reactions)
    insert_metabolites(conn, model_db_id, metabolites)
    insert_reaction_metabolites(conn, reaction_metabolites)

    conn.close()

    typer.echo(f"Semantic layer created: {out}")
    typer.echo(f"Reactions: {len(reactions)}")
    typer.echo(f"Metabolites: {len(metabolites)}")
    typer.echo(f"Reaction-metabolite links: {len(reaction_metabolites)}")