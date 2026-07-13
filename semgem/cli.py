from pathlib import Path
import typer

from semgem.io.load_model import load_sbml_model
from semgem.extract.extractor import Extractor
from semgem.database.sqlite import SemanticDatabase
from semgem.evidence.engine import EvidenceEngine
from semgem.evidence.load_rules import load_concept_definitions

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

    extractor = Extractor(model)
    reactions = extractor.extract_reactions()
    metabolites = extractor.extract_metabolites()
    reaction_metabolites = extractor.extract_stoichiometry()

    rules_path = Path(__file__).parent / "resources" / "evidence_rules.toml"
    concept_definitions = load_concept_definitions(rules_path)
    evidence_engine = EvidenceEngine(concept_definitions)
    semantic_concepts = evidence_engine.classify_reactions(reactions)

    schema_path = Path(__file__).parent / "database" / "schema.sql"
    database = SemanticDatabase(out, schema_path)
    database.initialise()
    model_db_id = database.insert_model(model, model_path)
    database.insert_reactions(model_db_id, reactions)
    database.insert_metabolites(model_db_id, metabolites)
    database.insert_reaction_metabolites(reaction_metabolites)
    database.insert_semantic_concepts(model_db_id,semantic_concepts)
    database.close()

    typer.echo(f"Semantic layer created: {out}")
    typer.echo(f"Reactions: {len(reactions)}")
    typer.echo(f"Metabolites: {len(metabolites)}")
    typer.echo(f"Reaction-metabolite links: {len(reaction_metabolites)}")
    typer.echo(f"Semantic concepts: {len(semantic_concepts)}")