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


def import_model(
    model_path: Path,
    database: SemanticDatabase,
    evidence_engine: EvidenceEngine,
) -> dict[str, int]:
    """Extract, classify, and import one SBML model into an open catalog."""
    model = load_sbml_model(model_path)

    extractor = Extractor(model)
    reactions = extractor.extract_reactions()
    metabolites = extractor.extract_metabolites()
    genes = extractor.extract_genes()
    reaction_metabolites = extractor.extract_stoichiometry()
    reaction_genes = extractor.extract_reaction_genes()

    semantic_concepts = evidence_engine.classify_reactions(reactions)

    database.import_model(
        model=model,
        source_file=str(model_path),
        content_hash=calculate_file_hash(model_path),
        reactions=reactions,
        metabolites=metabolites,
        genes=genes,
        stoichiometry=reaction_metabolites,
        reaction_genes=reaction_genes,
        concepts=semantic_concepts,
    )

    return {
        "reactions": len(reactions),
        "metabolites": len(metabolites),
        "genes": len(genes),
        "reaction_metabolites": len(reaction_metabolites),
        "reaction_genes": len(reaction_genes),
        "semantic_concepts": len(semantic_concepts),
    }

@app.callback()
def main():
    """
    semgem command line interface.
    """
    pass

@app.command()
def build(
    model_paths: list[Path] = typer.Argument(
        ...,
        help="One or more SBML model files to import into the catalog.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    out: Path = typer.Option(
        Path("outputs/semantic_layer.sqlite"),
        "--out",
        "-o",
        help="SQLite semantic catalog to create or extend.",
    ),
):
    """
    Build or extend one semantic catalog from one or more SBML models.
    """
    rules_path = Path(__file__).parent / "resources" / "evidence_rules.toml"
    concept_definitions = load_concept_definitions(rules_path)
    evidence_engine = EvidenceEngine(concept_definitions)
    schema_path = Path(__file__).parent / "database" / "schema.sql"
    imported = []

    try:
        with SemanticDatabase(out, schema_path) as database:
            database.initialise()
            for model_path in model_paths:
                counts = import_model(model_path, database, evidence_engine)
                imported.append((model_path, counts))
    except (
        DuplicateModelError,
        IncompatibleSchemaError,
        ModelIdentityConflictError,
    ) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error

    typer.echo(f"Semantic catalog: {out}")
    for model_path, counts in imported:
        typer.echo(f"Imported {model_path}:")
        typer.echo(f"  Reactions: {counts['reactions']}")
        typer.echo(f"  Metabolites: {counts['metabolites']}")
        typer.echo(f"  Genes: {counts['genes']}")
        typer.echo(
            f"  Reaction-metabolite links: {counts['reaction_metabolites']}"
        )
        typer.echo(f"  Reaction-gene links: {counts['reaction_genes']}")
        typer.echo(f"  Semantic concepts: {counts['semantic_concepts']}")
    typer.echo(f"Models imported: {len(imported)}")
