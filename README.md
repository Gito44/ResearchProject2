# SemGEM

SemGEM is a research prototype for generating an explainable semantic layer over SBML genome-scale metabolic models (GEMs).

Different GEMs often represent equivalent biological concepts using different combinations of reaction IDs, names, subsystem labels, SBML Groups, and external annotations. Code written for one model can therefore fail when applied to another model. SemGEM aims to normalize this heterogeneous information into a consistent, queryable representation for scientists and developers.

## Current capabilities

The current version can:

- load SBML models using COBRApy;
- extract reactions, metabolites, genes, stoichiometry, and gene associations;
- preserve existing model annotations as individually queryable identifiers;
- store multiple models in one relational SQLite catalog;
- assign configurable reaction-level semantic concepts using TOML evidence rules;
- record confidence, evidence fields, matched values, and evidence weights;
- detect exact duplicate models and model-identity conflicts;
- import each model atomically; and
- remove dependent model data through foreign-key cascades.

The package currently builds the semantic database. A public query API, JSON export, and external pathway enrichment are planned but not yet implemented.

## Installation

SemGEM requires Python 3.11 or later.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

For development and tests:

```bash
python -m pip install -e ".[dev]"
```

## Building a semantic catalog

```bash
semgem build path/to/model.xml --out outputs/semantic_catalog.sqlite
```

The same database can contain multiple models:

```bash
semgem build path/to/another_model.xml --out outputs/semantic_catalog.sqlite
```

SemGEM rejects an exact duplicate model. It also rejects reuse of an existing SBML model ID with different file content. Differently identified models with identical hashes are allowed with a warning.

## Testing

```bash
pytest
```

The current suite covers extraction, evidence operators, matched evidence values, relational insertion, annotation normalization, duplicate detection, atomic rollback, cascading deletion, entity-type validation, and file hashing.

## Architecture

```text
SBML model
    ↓
COBRApy loader
    ↓
typed extraction records
    ↓
configurable evidence engine
    ↓
multi-model SQLite semantic catalog
```

All reactions, metabolites, and genes receive a shared internal entity identity. Their original SBML identifiers are preserved. Type-specific tables store reaction, metabolite, and gene details, while annotations and semantic concepts reference the shared entity.

See [docs/database-schema.md](docs/database-schema.md) for the relational design.

## Evidence rules

Initial concept definitions are stored in:

```text
semgem/resources/evidence_rules.toml
```

The Python evidence engine applies these definitions without hard-coding individual biological concepts. Current rules are an early prototype and have not yet been biologically calibrated.

## Project scope

SemGEM is not:

- a replacement for COBRApy or ModelSEED;
- a new biological ontology;
- a model reconstruction or gap-filling system; or
- a source of definitive pathway truth.

Its intended contribution is a consistent, evidence-preserving interface over heterogeneous model semantics and established external resources.

## Documentation

- [Project reasoning and preliminary findings](docs/project_reasoning.md)
- [Database schema](docs/database-schema.md)
- [Future work](docs/future_work.md)
- [Living TODO list](docs/todo.md)

## Current limitations

- Only initial reaction-level concepts are classified.
- Confidence scores use simple additive rule weights and are not calibrated probabilities.
- KEGG, SBO, MetaNetX, and other external enrichment workflows are not yet implemented beyond annotations already present in source models.
- Query commands and a public Python query interface are not yet implemented.
- The current SQLite schema is regenerated during development; schema migrations are not supported.
- Databases generated with the earlier prototype schema must be rebuilt from their source model files.
- External resource licensing and redistribution requirements must be considered before publishing enriched datasets.
