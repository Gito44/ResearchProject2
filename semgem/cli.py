from pathlib import Path
import typer

from semgem.io.load_model import calculate_file_hash, load_sbml_model
from semgem.extract.extractor import Extractor
from semgem.database.sqlite import (
    DuplicateModelError,
    IncompatibleSchemaError,
    ModelIdentityConflictError,
    SemanticDatabase,
)
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
    genes = extractor.extract_genes()
    reaction_metabolites = extractor.extract_stoichiometry()
    reaction_genes = extractor.extract_reaction_genes()

    rules_path = Path(__file__).parent / "resources" / "evidence_rules.toml"
    concept_definitions = load_concept_definitions(rules_path)
    evidence_engine = EvidenceEngine(concept_definitions)
    semantic_concepts = evidence_engine.classify_reactions(reactions)

    schema_path = Path(__file__).parent / "database" / "schema.sql"
    content_hash = calculate_file_hash(model_path)
    try:
        with SemanticDatabase(out, schema_path) as database:
            database.initialise()
            database.import_model(
                model=model,
                source_file=model_path,
                content_hash=content_hash,
                reactions=reactions,
                metabolites=metabolites,
                genes=genes,
                stoichiometry=reaction_metabolites,
                reaction_genes=reaction_genes,
                concepts=semantic_concepts,
            )
    except (
        DuplicateModelError,
        IncompatibleSchemaError,
        ModelIdentityConflictError,
    ) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error

    typer.echo(f"Semantic layer created: {out}")
    typer.echo(f"Reactions: {len(reactions)}")
    typer.echo(f"Metabolites: {len(metabolites)}")
    typer.echo(f"Genes: {len(genes)}")
    typer.echo(f"Reaction-metabolite links: {len(reaction_metabolites)}")
    typer.echo(f"Reaction-gene links: {len(reaction_genes)}")
    typer.echo(f"Semantic concepts: {len(semantic_concepts)}")
