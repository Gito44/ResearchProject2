from dataclasses import asdict
import json
from pathlib import Path
import sys
import typer

from semgem.io.load_model import calculate_file_hash, load_sbml_model
from semgem.extract.extractor import Extractor
from semgem.database.sqlite import (
    DuplicateModelError,
    IncompatibleSchemaError,
    ModelIdentityConflictError,
    SemanticDatabase,
)
from semgem.enrichment import (
    KeggProvider,
    MetaNetXChemistryProvider,
    MetaNetXProvider,
    RheaProvider,
    SBOProvider,
)
from semgem.evidence.concepts import ConceptRegistry
from semgem.evidence.load_rules import load_concepts, load_evidence_policy
from semgem.export import JsonCatalogExporter, package_version
from semgem.pipeline import SemanticPipeline
from semgem.query import (
    ConceptNotFoundError,
    EntityNotFoundError,
    SemanticCatalog,
)
from semgem.resources_manager import (
    ResourceManager,
    ResourceUnavailableError,
    default_resource_root,
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
) -> dict[str, int]:
    """Extract and import one raw SBML model baseline into an open catalog."""
    model = load_sbml_model(model_path)
    if not str(model.id or "").strip():
        raise ValueError(
            f"Model file '{model_path}' has no usable SBML model ID. "
            "SemGEM requires a source model ID for safe multi-model identity."
        )

    extractor = Extractor(model)
    reactions = extractor.extract_reactions()
    metabolites = extractor.extract_metabolites()
    genes = extractor.extract_genes()
    reaction_metabolites = extractor.extract_stoichiometry()
    reaction_genes = extractor.extract_reaction_genes()

    database.import_model(
        model=model,
        source_file=str(model_path),
        content_hash=calculate_file_hash(model_path),
        reactions=reactions,
        metabolites=metabolites,
        genes=genes,
        stoichiometry=reaction_metabolites,
        reaction_genes=reaction_genes,
    )

    return {
        "reactions": len(reactions),
        "metabolites": len(metabolites),
        "genes": len(genes),
        "reaction_metabolites": len(reaction_metabolites),
        "reaction_genes": len(reaction_genes),
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


def format_option():
    return typer.Option(
        "text",
        "--format",
        help="Output format: text or json.",
    )


def validate_format(output_format: str) -> str:
    output_format = output_format.lower()
    if output_format not in {"text", "json"}:
        raise typer.BadParameter("--format must be 'text' or 'json'.")
    return output_format


def echo_json(value) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2))


def model_payload(model) -> dict:
    return {
        "id": model.original_id,
        "name": model.name,
        "source_file": model.source_file,
        "content_hash": model.content_hash,
    }


def entity_payload(entity) -> dict:
    return {
        "model_id": entity.model_id,
        "entity_type": entity.entity_type,
        "id": entity.original_id,
        "name": entity.name,
    }


def explanation_payload(result) -> dict:
    return {
        "id": result.name,
        "label": result.preferred_label,
        "confidence": result.confidence,
        "evidence": [
            {
                "code": evidence.evidence_code,
                "source": evidence.source,
                "observed_value": evidence.observed_value,
                "explanation": evidence.explanation,
                "weight": evidence.weight,
            }
            for evidence in result.evidence
        ],
    }


def concept_payload(concept) -> dict:
    return {
        "id": concept.name,
        "label": concept.preferred_label,
        "confidence": concept.confidence,
    }


def coverage_payload(result) -> dict:
    total = result.total_reactions

    def fraction(value: int) -> float:
        return value / total if total else 0.0

    return {
        **asdict(result),
        "pathway_coverage": fraction(result.pathway_reactions),
        "actionable_non_pathway_coverage": fraction(
            result.actionable_non_pathway_reactions
        ),
        "actionable_coverage": fraction(result.actionable_reactions),
        "generic_only_coverage": fraction(result.generic_only_reactions),
        "unclassified_coverage": fraction(result.unclassified_reactions),
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
    kegg: bool | None = typer.Option(
        None,
        "--kegg/--no-kegg",
        help=(
            "Use optional KEGG REST enrichment. Requires internet access and "
            "takes longer; users are responsible for complying with KEGG terms."
        ),
    ),
    sbo_file: Path | None = typer.Option(
        None,
        "--sbo-file",
        help="Advanced override for the managed SBO OBO resource.",
        hidden=True,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    metanetx_xref: Path | None = typer.Option(
        None,
        "--metanetx-xref",
        help=(
            "Advanced override for the managed MNXref reac_xref.tsv resource."
        ),
        hidden=True,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    metanetx_chem_xref: Path | None = typer.Option(
        None,
        "--metanetx-chem-xref",
        help="Advanced override for the managed MNXref chem_xref.tsv resource.",
        hidden=True,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    metanetx_reac_prop: Path | None = typer.Option(
        None,
        "--metanetx-reac-prop",
        help=(
            "Advanced override for the managed MNXref reac_prop.tsv resource."
        ),
        hidden=True,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    metanetx_chem_prop: Path | None = typer.Option(
        None,
        "--metanetx-chem-prop",
        help=(
            "Advanced optional override for MNXref chem_prop.tsv."
        ),
        hidden=True,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    rhea_xref: Path | None = typer.Option(
        None,
        "--rhea-xref",
        help=(
            "Advanced override for the managed Rhea rhea2xrefs.tsv resource."
        ),
        hidden=True,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    metanetx: bool = typer.Option(
        True,
        "--metanetx/--no-metanetx",
        help=(
            "Use MetaNetX enrichment. Missing official release files are "
            "downloaded into SemGEM's managed resource cache."
        ),
    ),
    metanetx_chemistry: bool = typer.Option(
        False,
        "--metanetx-chemistry/--no-metanetx-chemistry",
        help=(
            "Use MetaNetX metabolite and stoichiometric enrichment. This "
            "requires a large first-run download (currently over 650 MB)."
        ),
    ),
    rhea: bool = typer.Option(
        True,
        "--rhea/--no-rhea",
        help=(
            "Use Rhea enrichment. A missing official xref file is downloaded "
            "into SemGEM's managed resource cache."
        ),
    ),
    resource_dir: Path | None = typer.Option(
        None,
        "--resource-dir",
        help=(
            "Managed provider resource directory (default: "
            "~/.semgem/resources or SEMGEM_RESOURCE_DIR)."
        ),
    ),
    refresh_resources: bool = typer.Option(
        False,
        "--refresh-resources",
        help="Download fresh copies of enabled managed provider resources.",
    ),
    offline: bool = typer.Option(
        False,
        "--offline",
        help="Never download provider resources; require verified cached files.",
    ),
    use_subsystems: bool = typer.Option(
        True,
        "--use-subsystems/--ignore-subsystems",
        help=(
            "Use source-model subsystem labels as semantic evidence. "
            "Disable this when evaluating static inference."
        ),
    ),
):
    """
    Build or extend one semantic catalog from one or more SBML models.
    """
    resources_path = Path(__file__).parent / "resources"
    concepts = load_concepts(resources_path / "concepts.toml")
    policy = load_evidence_policy(
        resources_path / "evidence_rules.toml",
        concepts,
    )
    registry = ConceptRegistry(concepts)
    schema_path = Path(__file__).parent / "database" / "schema.sql"
    resource_manager = ResourceManager(
        resource_dir,
        packaged_sbo=resources_path / "sbo" / "SBO_OBO.obo",
        download_reporter=lambda spec, path: typer.echo(
            f"Downloading {spec.provider} {spec.version} {spec.filename} "
            f"to {path} ..."
        ),
    )
    discovered_models = discover_model_paths(model_paths)
    if metanetx_chemistry and not metanetx:
        raise typer.BadParameter(
            "--metanetx-chemistry requires MetaNetX enrichment; remove "
            "--no-metanetx."
        )
    imported = []
    if kegg is None:
        if sys.stdin.isatty():
            kegg = typer.confirm(
                "Enable recommended KEGG enrichment? "
                "This requires internet access and takes longer",
                default=False,
            )
        else:
            kegg = False

    try:
        managed_resources = []
        if sbo_file is None:
            managed = resource_manager.ensure(
                "sbo_obo", refresh=refresh_resources, offline=offline
            )
            sbo_file = managed.path
            managed_resources.append(managed)
        if rhea and rhea_xref is None:
            managed = resource_manager.ensure(
                "rhea_xref", refresh=refresh_resources, offline=offline
            )
            rhea_xref = managed.path
            managed_resources.append(managed)
        if metanetx:
            requested_mnx = {"metanetx_reac_xref": metanetx_xref}
            chemistry_requested = metanetx_chemistry or any(
                path is not None
                for path in (
                    metanetx_chem_xref,
                    metanetx_reac_prop,
                    metanetx_chem_prop,
                )
            )
            if chemistry_requested:
                requested_mnx.update(
                    {
                        "metanetx_chem_xref": metanetx_chem_xref,
                        "metanetx_reac_prop": metanetx_reac_prop,
                    }
                )
            resolved_mnx = {}
            for key, explicit_path in requested_mnx.items():
                if explicit_path is not None:
                    resolved_mnx[key] = explicit_path
                    continue
                managed = resource_manager.ensure(
                    key, refresh=refresh_resources, offline=offline
                )
                resolved_mnx[key] = managed.path
                managed_resources.append(managed)
            metanetx_xref = resolved_mnx["metanetx_reac_xref"]
            if chemistry_requested:
                metanetx_chem_xref = resolved_mnx["metanetx_chem_xref"]
                metanetx_reac_prop = resolved_mnx["metanetx_reac_prop"]

        with SemanticDatabase(out, schema_path) as database:
            database.initialise()
            for model_path in discovered_models:
                counts = import_model(model_path, database)
                imported.append((model_path, counts))
            providers = [SBOProvider(sbo_file)]
            if metanetx and metanetx_chem_xref is not None:
                providers.append(
                    MetaNetXChemistryProvider(
                        chem_xref_path=metanetx_chem_xref,
                        chem_prop_path=metanetx_chem_prop,
                        reac_prop_path=metanetx_reac_prop,
                        reac_xref_path=metanetx_xref,
                    )
                )
            if metanetx and metanetx_xref is not None:
                providers.append(MetaNetXProvider(metanetx_xref))
            if rhea and rhea_xref is not None:
                providers.append(RheaProvider(rhea_xref))
            if kegg:
                providers.append(KeggProvider())
            pipeline_summary = SemanticPipeline(registry, policy).run(
                database,
                providers,
                include_subsystem_evidence=use_subsystems,
            )
            database.set_catalog_metadata(
                {
                    "package_version": package_version(),
                    "semantic_schema_version": "1.0",
                    "subsystem_evidence_enabled": use_subsystems,
                    "concepts_sha256": calculate_file_hash(
                        resources_path / "concepts.toml"
                    ),
                    "evidence_policy_sha256": calculate_file_hash(
                        resources_path / "evidence_rules.toml"
                    ),
                    "managed_resources": [
                        {
                            **asdict(resource),
                            "path": str(resource.path),
                        }
                        for resource in managed_resources
                    ],
                }
            )
    except (
        DuplicateModelError,
        IncompatibleSchemaError,
        ModelIdentityConflictError,
        ResourceUnavailableError,
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
    typer.echo(f"Models imported: {len(imported)}")
    for provider in pipeline_summary.providers:
        typer.echo(
            f"{provider.provider.upper()} enrichment: {provider.status} "
            f"(resolved {provider.resolved}/{provider.requested}, "
            f"unresolved {provider.unresolved})"
        )
        for warning in provider.warnings:
            typer.echo(f"  Warning: {warning}")
    typer.echo(f"Candidate evidence evaluated: {pipeline_summary.candidate_count}")
    typer.echo(f"Semantic concepts assigned: {pipeline_summary.concept_count}")
    if not kegg:
        typer.echo(
            "KEGG enrichment was not used. Build a new catalogue with --kegg "
            "for recommended online pathway enrichment."
        )


@app.command("resources")
def resources_status(
    resource_dir: Path | None = typer.Option(
        None,
        "--resource-dir",
        help=(
            "Managed resource directory (default: ~/.semgem/resources or "
            "SEMGEM_RESOURCE_DIR)."
        ),
    ),
    output_format: str = format_option(),
):
    """Show the availability, version, and integrity of provider resources."""
    output_format = validate_format(output_format)
    manager = ResourceManager(resource_dir)
    results = manager.status()
    if output_format == "json":
        echo_json(
            {
                "resource_dir": str(resource_dir or default_resource_root()),
                "resources": results,
            }
        )
        return
    typer.echo(f"Resource directory: {resource_dir or default_resource_root()}")
    for result in results:
        status = "verified" if result["verified"] else (
            "unverified" if result["available"] else "missing"
        )
        typer.echo(
            f"{result['key']}\t{status}\tversion={result['version']}\t"
            f"{result['path']}"
        )


@app.command("export")
def export_catalog(
    catalog_path: Path = catalog_argument(),
    out: Path = typer.Option(
        ...,
        "--out",
        "-o",
        help="Local JSON file to create.",
    ),
    model_ids: list[str] | None = typer.Option(
        None,
        "--model",
        "-m",
        help="Export only this model; repeat to select multiple models.",
    ),
    include_evidence: bool = typer.Option(
        True,
        "--evidence/--no-evidence",
        help="Include or omit evidence supporting semantic assignments.",
    ),
    compact: bool = typer.Option(
        False,
        "--compact",
        help="Write compact JSON instead of indented human-readable JSON.",
    ),
    gzip_output: bool = typer.Option(
        False,
        "--gzip",
        help="Compress the JSON export with gzip (also enabled by a .gz suffix).",
    ),
):
    """Export a local semantic catalog to versioned, portable JSON."""
    resources = Path(__file__).parent / "resources"
    try:
        with SemanticCatalog(catalog_path) as catalog:
            exporter = JsonCatalogExporter(catalog, resources / "concepts.toml")
            exporter.write(
                out,
                model_ids=model_ids,
                include_evidence=include_evidence,
                compact=compact,
                compress=gzip_output or out.suffix.lower() == ".gz",
            )
            contains_kegg = any(
                run.provider == "kegg" for run in catalog.list_provider_runs()
            )
    except (EntityNotFoundError, ValueError) as error:
        query_error(error)

    typer.echo(f"JSON catalog: {out}")
    if contains_kegg:
        typer.echo(
            "Notice: this local export contains KEGG-derived enrichment. "
            "Review applicable KEGG terms before redistributing it."
        )


@app.command()
def models(
    catalog_path: Path = catalog_argument(),
    output_format: str = format_option(),
):
    """List models stored in a semantic catalog."""
    with SemanticCatalog(catalog_path) as catalog:
        stored_models = catalog.list_models()

    output_format = validate_format(output_format)
    if output_format == "json":
        echo_json([model_payload(model) for model in stored_models])
        return
    if not stored_models:
        typer.echo("No models found.")
        return

    for model in stored_models:
        name = model.name or ""
        typer.echo(f"{model.original_id}\t{name}")


@app.command()
def summary(
    catalog_path: Path = catalog_argument(),
    model_id: str | None = typer.Option(
        None, "--model", "-m", help="Limit the summary to one SBML model ID."
    ),
    output_format: str = format_option(),
):
    """Summarize catalog contents and accepted semantic assignments."""
    try:
        with SemanticCatalog(catalog_path) as catalog:
            result = catalog.statistics(model_id)
    except EntityNotFoundError as error:
        query_error(error)

    output_format = validate_format(output_format)
    if output_format == "json":
        echo_json({"scope": model_id, **asdict(result)})
        return
    typer.echo(f"scope\t{model_id or 'all models'}")
    typer.echo(f"models\t{result.model_count}")
    typer.echo(f"reactions\t{result.reaction_count}")
    typer.echo(f"metabolites\t{result.metabolite_count}")
    typer.echo(f"genes\t{result.gene_count}")
    typer.echo(f"semantic_assignments\t{result.semantic_assignment_count}")


def echo_coverage(result) -> None:
    """Print one coverage summary using mutually interpretable states."""
    total = result.total_reactions

    def percent(value: int) -> float:
        return 100 * value / total if total else 0.0

    typer.echo(f"scope\t{result.model_id or 'all models'}")
    typer.echo(f"total_reactions\t{total}")
    typer.echo(
        f"pathway\t{result.pathway_reactions}\t"
        f"{percent(result.pathway_reactions):.2f}%"
    )
    typer.echo(
        f"actionable_non_pathway_only\t"
        f"{result.actionable_non_pathway_reactions}\t"
        f"{percent(result.actionable_non_pathway_reactions):.2f}%"
    )
    typer.echo(
        f"actionable_total\t{result.actionable_reactions}\t"
        f"{percent(result.actionable_reactions):.2f}%"
    )
    typer.echo(
        f"generic_only\t{result.generic_only_reactions}\t"
        f"{percent(result.generic_only_reactions):.2f}%"
    )
    typer.echo(
        f"unclassified\t{result.unclassified_reactions}\t"
        f"{percent(result.unclassified_reactions):.2f}%"
    )


@app.command()
def coverage(
    catalog_path: Path = catalog_argument(),
    model_id: str | None = typer.Option(
        None, "--model", "-m", help="Limit coverage to one SBML model ID."
    ),
    output_format: str = format_option(),
):
    """Report pathway, actionable, generic-only and unclassified reactions."""
    try:
        with SemanticCatalog(catalog_path) as catalog:
            result = catalog.coverage(model_id)
    except EntityNotFoundError as error:
        query_error(error)
    output_format = validate_format(output_format)
    if output_format == "json":
        echo_json(coverage_payload(result))
    else:
        echo_coverage(result)


@app.command("get-concept")
def get_concept(
    catalog_path: Path = catalog_argument(),
    concept_name: str = typer.Option(
        ..., "--concept", "-c", help="Canonical semantic concept identifier."
    ),
    model_id: str | None = typer.Option(
        None, "--model", "-m", help="Limit results to one SBML model ID."
    ),
    minimum_confidence: float = typer.Option(
        0.0,
        "--min-confidence",
        min=0.0,
        max=1.0,
        help="Minimum accepted evidence score.",
    ),
    limit: int = typer.Option(100, "--limit", "-n", min=1),
    output_format: str = format_option(),
):
    """List model entities assigned to one canonical semantic concept."""
    try:
        with SemanticCatalog(catalog_path) as catalog:
            results = catalog.get_concept_assignments(
                concept_name,
                model_id=model_id,
                minimum_confidence=minimum_confidence,
                limit=limit,
            )
    except (EntityNotFoundError, ValueError) as error:
        query_error(error)
    output_format = validate_format(output_format)
    if output_format == "json":
        echo_json(
            [
                {
                    "entity": entity_payload(result.entity),
                    "concept": concept_payload(result.concept),
                }
                for result in results
            ]
        )
        return
    if not results:
        typer.echo("No concept assignments found.")
        return
    for result in results:
        entity = result.entity
        typer.echo(
            f"{entity.model_id}\t{entity.entity_type}\t{entity.original_id}\t"
            f"{entity.name or ''}\tconfidence={result.concept.confidence:.3f}"
        )


@app.command()
def unclassified(
    catalog_path: Path = catalog_argument(),
    model_id: str | None = typer.Option(
        None, "--model", "-m", help="Limit results to one SBML model ID."
    ),
    limit: int = typer.Option(100, "--limit", "-n", min=1),
    output_format: str = format_option(),
):
    """List reactions with no accepted semantic conclusion."""
    try:
        with SemanticCatalog(catalog_path) as catalog:
            results = catalog.list_unclassified_reactions(model_id, limit)
    except (EntityNotFoundError, ValueError) as error:
        query_error(error)
    output_format = validate_format(output_format)
    if output_format == "json":
        echo_json([entity_payload(result) for result in results])
        return
    if not results:
        typer.echo("No unclassified reactions found.")
        return
    for result in results:
        typer.echo(
            f"{result.model_id}\treaction\t{result.original_id}\t"
            f"{result.name or ''}"
        )


@app.command()
def providers(
    catalog_path: Path = catalog_argument(),
    output_format: str = format_option(),
):
    """List provider runs, versions, resolution counts and failures."""
    with SemanticCatalog(catalog_path) as catalog:
        results = catalog.list_provider_runs()
    output_format = validate_format(output_format)
    if output_format == "json":
        echo_json([asdict(result) for result in results])
        return
    if not results:
        typer.echo("No provider runs found.")
        return
    for result in results:
        typer.echo(
            f"{result.provider}\t{result.status}\t"
            f"version={result.resource_version or ''}\t"
            f"resolved={result.resolved}/{result.requested}\t"
            f"unresolved={result.unresolved}\t"
            f"error={result.error_summary or ''}"
        )


@app.command()
def compare(
    catalog_path: Path = catalog_argument(),
    model_ids: list[str] = typer.Option(
        ..., "--model", "-m", help="Model ID to compare; provide at least twice."
    ),
    output_format: str = format_option(),
):
    """Compare semantic coverage for two or more models in one catalog."""
    unique_model_ids = list(dict.fromkeys(model_ids))
    if len(unique_model_ids) < 2:
        raise typer.BadParameter("Provide at least two distinct --model values.")
    try:
        with SemanticCatalog(catalog_path) as catalog:
            results = [catalog.coverage(model_id) for model_id in unique_model_ids]
    except EntityNotFoundError as error:
        query_error(error)

    output_format = validate_format(output_format)
    if output_format == "json":
        echo_json([coverage_payload(result) for result in results])
        return
    typer.echo(
        "model\treactions\tpathway\tactionable_non_pathway\t"
        "actionable_total\tgeneric_only\tunclassified"
    )
    for result in results:
        total = result.total_reactions

        def percent(value: int) -> str:
            return f"{100 * value / total:.2f}%" if total else "0.00%"

        typer.echo(
            f"{result.model_id}\t{total}\t"
            f"{percent(result.pathway_reactions)}\t"
            f"{percent(result.actionable_non_pathway_reactions)}\t"
            f"{percent(result.actionable_reactions)}\t"
            f"{percent(result.generic_only_reactions)}\t"
            f"{percent(result.unclassified_reactions)}"
        )


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
    output_format: str = format_option(),
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

    output_format = validate_format(output_format)
    if output_format == "json":
        echo_json(
            [
                {
                    "entity": entity_payload(result.entity),
                    "matches": [asdict(match) for match in result.matches],
                }
                for result in results
            ]
        )
        return
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
    output_format: str = format_option(),
):
    """Show one model entity."""
    try:
        with SemanticCatalog(catalog_path) as catalog:
            result = catalog.get_entity(model_id, entity_type, entity_id)
    except (EntityNotFoundError, ValueError) as error:
        query_error(error)

    output_format = validate_format(output_format)
    if output_format == "json":
        echo_json(entity_payload(result))
        return
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
    output_format: str = format_option(),
):
    """List annotations attached to one model entity."""
    try:
        with SemanticCatalog(catalog_path) as catalog:
            results = catalog.get_annotations(model_id, entity_type, entity_id)
    except (EntityNotFoundError, ValueError) as error:
        query_error(error)

    output_format = validate_format(output_format)
    if output_format == "json":
        echo_json([asdict(result) for result in results])
        return
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
    output_format: str = format_option(),
):
    """List semantic concepts assigned to one model entity."""
    try:
        with SemanticCatalog(catalog_path) as catalog:
            results = catalog.get_concepts(model_id, entity_type, entity_id)
    except (EntityNotFoundError, ValueError) as error:
        query_error(error)

    output_format = validate_format(output_format)
    if output_format == "json":
        echo_json([concept_payload(result) for result in results])
        return
    if not results:
        typer.echo("No semantic concepts found.")
        return

    for result in results:
        typer.echo(
            f"{result.name}\t{result.preferred_label}\t"
            f"confidence={result.confidence:.3f}"
        )


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
    output_format: str = format_option(),
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

    output_format = validate_format(output_format)
    if output_format == "json":
        echo_json(explanation_payload(result))
        return
    typer.echo(
        f"{result.name}\t{result.preferred_label}\t"
        f"confidence={result.confidence:.3f}"
    )
    for evidence in result.evidence:
        observed = evidence.observed_value or ""
        typer.echo(
            f"{evidence.evidence_code}\t"
            f"source={evidence.source}\t"
            f"observed={observed}\t"
            f"weight={evidence.weight:.3f}\t"
            f"{evidence.explanation}"
        )
