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
from semgem.query import (
    ConceptNotFoundError,
    EntityNotFoundError,
    SemanticCatalog,
)

app = typer.Typer()
SUPPORTED_MODEL_SUFFIXES = (".xml", ".xml.gz", ".sbml", ".sbml.gz")


def is_supported_model_file(path: Path) -> bool:
    """Return whether a path has a supported SBML filename suffix."""
    name = path.name.lower()
    return path.is_file() and any(
        name.endswith(suffix) for suffix in SUPPORTED_MODEL_SUFFIXES
    )


def discover_model_paths(input_paths: list[Path]) -> list[Path]:
    """Expand files and directories into unique, deterministically ordered models."""
    discovered: dict[Path, Path] = {}

    for input_path in input_paths:
        if input_path.is_dir():
            candidates = (
                path for path in input_path.rglob("*") if is_supported_model_file(path)
            )
        elif is_supported_model_file(input_path):
            candidates = (input_path,)
        else:
            supported = ", ".join(SUPPORTED_MODEL_SUFFIXES)
            raise typer.BadParameter(
                f"Unsupported model file '{input_path}'. Expected: {supported}."
            )

        for candidate in candidates:
            resolved = candidate.resolve()
            discovered.setdefault(resolved, candidate)

    if not discovered:
        supported = ", ".join(SUPPORTED_MODEL_SUFFIXES)
        raise typer.BadParameter(
            f"No supported SBML model files were found. Expected: {supported}."
        )

    return [discovered[path] for path in sorted(discovered, key=str)]


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


def catalog_argument() -> typer.Argument:
    return typer.Argument(
        ...,
        help="SemGEM SQLite catalog to query.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    )


def query_options():
    return {
        "model_id": typer.Option(..., "--model", "-m", help="SBML model ID."),
        "entity_type": typer.Option(
            ...,
            "--type",
            "-t",
            help="Entity type: reaction, metabolite, or gene.",
        ),
        "entity_id": typer.Option(
            ...,
            "--id",
            help="Original entity identifier within the model.",
        ),
    }


def query_error(error: Exception) -> None:
    typer.echo(f"Error: {error}", err=True)
    raise typer.Exit(code=1) from error

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
        help="One or more SBML files or directories to import into the catalog.",
        exists=True,
        file_okay=True,
        dir_okay=True,
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
    discovered_models = discover_model_paths(model_paths)
    imported = []

    try:
        with SemanticDatabase(out, schema_path) as database:
            database.initialise()
            for model_path in discovered_models:
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


@app.command()
def models(catalog_path: Path = catalog_argument()):
    """List models stored in a semantic catalog."""
    with SemanticCatalog(catalog_path) as catalog:
        stored_models = catalog.list_models()

    if not stored_models:
        typer.echo("No models found.")
        return

    for model in stored_models:
        name = model.name or ""
        typer.echo(f"{model.original_id}\t{name}")


@app.command()
def search(
    catalog_path: Path = catalog_argument(),
    query: str = typer.Argument(..., help="Text to search for."),
    model_id: str | None = typer.Option(
        None, "--model", "-m", help="Limit results to one SBML model ID."
    ),
    entity_type: str | None = typer.Option(
        None,
        "--type",
        "-t",
        help="Limit results to reactions, metabolites, or genes.",
    ),
    annotation_source: str | None = typer.Option(
        None,
        "--source",
        "-s",
        help="Search only identifiers from this annotation source.",
    ),
    limit: int = typer.Option(
        100,
        "--limit",
        "-n",
        min=1,
        help="Maximum number of matching entities.",
    ),
):
    """Search entities across one or many models."""
    try:
        with SemanticCatalog(catalog_path) as catalog:
            results = catalog.search(
                query=query,
                model_id=model_id,
                entity_type=entity_type,
                annotation_source=annotation_source,
                limit=limit,
            )
    except ValueError as error:
        query_error(error)

    if not results:
        typer.echo("No matches found.")
        return

    for result in results:
        entity = result.entity
        matches = []
        for match in result.matches:
            field = match.field
            if match.source is not None:
                field = f"{field}[{match.source}]"
            matches.append(f"{field}={match.value}")
        typer.echo(
            f"{entity.model_id}\t{entity.entity_type}\t"
            f"{entity.original_id}\t{entity.name or ''}\t"
            f"matches: {', '.join(matches)}"
        )


@app.command()
def entity(
    catalog_path: Path = catalog_argument(),
    model_id: str = query_options()["model_id"],
    entity_type: str = query_options()["entity_type"],
    entity_id: str = query_options()["entity_id"],
):
    """Show one model entity."""
    try:
        with SemanticCatalog(catalog_path) as catalog:
            result = catalog.get_entity(model_id, entity_type, entity_id)
    except (EntityNotFoundError, ValueError) as error:
        query_error(error)

    typer.echo(f"internal_id\t{result.internal_id}")
    typer.echo(f"model\t{result.model_id}")
    typer.echo(f"type\t{result.entity_type}")
    typer.echo(f"id\t{result.original_id}")
    typer.echo(f"name\t{result.name or ''}")


@app.command()
def annotations(
    catalog_path: Path = catalog_argument(),
    model_id: str = query_options()["model_id"],
    entity_type: str = query_options()["entity_type"],
    entity_id: str = query_options()["entity_id"],
):
    """List annotations attached to one model entity."""
    try:
        with SemanticCatalog(catalog_path) as catalog:
            results = catalog.get_annotations(model_id, entity_type, entity_id)
    except (EntityNotFoundError, ValueError) as error:
        query_error(error)

    if not results:
        typer.echo("No annotations found.")
        return

    for result in results:
        typer.echo(f"{result.source}\t{result.identifier}")


@app.command()
def concepts(
    catalog_path: Path = catalog_argument(),
    model_id: str = query_options()["model_id"],
    entity_type: str = query_options()["entity_type"],
    entity_id: str = query_options()["entity_id"],
):
    """List semantic concepts assigned to one model entity."""
    try:
        with SemanticCatalog(catalog_path) as catalog:
            results = catalog.get_concepts(model_id, entity_type, entity_id)
    except (EntityNotFoundError, ValueError) as error:
        query_error(error)

    if not results:
        typer.echo("No semantic concepts found.")
        return

    for result in results:
        typer.echo(f"{result.name}\tconfidence={result.confidence:.3f}")


@app.command()
def explain(
    catalog_path: Path = catalog_argument(),
    model_id: str = query_options()["model_id"],
    entity_type: str = query_options()["entity_type"],
    entity_id: str = query_options()["entity_id"],
    concept_name: str = typer.Option(
        ...,
        "--concept",
        "-c",
        help="Semantic concept to explain.",
    ),
):
    """Explain the evidence supporting one semantic concept assignment."""
    try:
        with SemanticCatalog(catalog_path) as catalog:
            result = catalog.explain_concept(
                model_id,
                entity_type,
                entity_id,
                concept_name,
            )
    except (ConceptNotFoundError, EntityNotFoundError, ValueError) as error:
        query_error(error)

    typer.echo(f"{result.name}\tconfidence={result.confidence:.3f}")
    for evidence in result.evidence:
        matched = evidence.matched_value or ""
        typer.echo(
            f"{evidence.evidence_type}\t"
            f"field={evidence.target_field}\t"
            f"matched={matched}\t"
            f"weight={evidence.weight:.3f}\t"
            f"{evidence.text}"
        )
