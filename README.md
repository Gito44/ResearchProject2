# SemGEM

SemGEM is a research prototype for generating an explainable semantic layer over SBML genome-scale metabolic models (GEMs).

Different GEMs often represent equivalent biological concepts using different combinations of reaction IDs, names, subsystem labels, SBML Groups, and external annotations. Code written for one model can therefore fail when applied to another model. SemGEM aims to normalize this heterogeneous information into a consistent, queryable representation for scientists and developers.

## Current capabilities

The current version can:

- load SBML models using COBRApy;
- extract reactions, metabolites, genes, stoichiometry, and gene associations;
- preserve existing model annotations as individually queryable identifiers;
- store multiple models in one relational SQLite catalog;
- resolve SBO annotations against a packaged, licensed ontology snapshot;
- bridge reaction identities through user-supplied official MetaNetX and Rhea
  cross-reference files;
- classify a small, transparent set of central-metabolism community reaction
  IDs through exact equality rules;
- infer translocation and compartment-specific transport from reaction
  stoichiometry and the model's named compartments;
- treat annotation-free BiGG-style local reaction IDs as lookup candidates
  that must be confirmed by a user-supplied MetaNetX table;
- recognize strict KEGG, Rhea, and MetaNetX accessions used directly as local
  reaction IDs without fabricating source annotations;
- optionally resolve KEGG reaction-to-pathway relationships at runtime;
- normalize external labels to provider-independent canonical concepts;
- query models, scoped entities, annotations, concepts, and supporting evidence
  through a read-only Python API;
- generate fixed evidence templates dynamically from model and provider facts;
- score candidates using configurable provisional TOML weights and thresholds;
- record confidence, observed values, provider provenance, and evidence weights;
- detect exact duplicate models and model-identity conflicts;
- import each model atomically; and
- remove dependent model data through foreign-key cascades.

The package currently builds, enriches, classifies, and queries the semantic
database. JSON export is not yet implemented.

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

One command can import multiple models into the same catalog:

```bash
semgem build path/to/model_a.xml path/to/model_b.xml \
    --out outputs/semantic_catalog.sqlite
```

Single-model commands remain supported. A later command can also extend the same
catalog by importing another model.

A directory can be imported recursively, which is more convenient for larger
model collections:

```bash
semgem build path/to/models/ --out outputs/semantic_catalog.sqlite
```

SBO enrichment runs locally by default. KEGG enrichment is recommended but
optional because it needs internet access, takes longer, and has separate usage
conditions:

```bash
semgem build path/to/models/ \
    --out outputs/semantic_catalog.sqlite \
    --kegg
```

Automated workflows should explicitly use `--kegg` or `--no-kegg`. SemGEM does
not distribute static KEGG mappings. Runtime results are stored only in the
user's local catalog; users remain responsible for complying with KEGG terms
and should not redistribute KEGG-derived catalogs without appropriate
permission.

MetaNetX and Rhea identity bridging is enabled by passing official downloaded
cross-reference files. SemGEM deliberately does not bundle these datasets:

```bash
semgem build path/to/models/ \
    --out outputs/semantic_catalog.sqlite \
    --metanetx-xref path/to/reac_xref.tsv \
    --rhea-xref path/to/rhea2xrefs.tsv \
    --kegg
```

The identity providers run before KEGG, allowing model BiGG, MetaNetX, or Rhea
annotations to expose additional KEGG reaction identifiers. KEGG then obtains
pathway relationships at runtime in batches. MetaNetX and Rhea improve identity
reach; they do not themselves imply pathway membership.

Official sources:

- MetaNetX `reac_xref.tsv`:
  `https://www.metanetx.org/mnxdoc/mnxref.html`
- Rhea `rhea2xrefs.tsv`:
  `https://www.rhea-db.org/help/download`

Rhea data is CC BY 4.0. MetaNetX is generally CC BY 4.0 but warns that
cross-referenced records may retain restrictions from their original sources.
Users should retain provenance and review the applicable source terms before
redistributing enriched catalogs.

Experimental exact community-ID rules are enabled in v0.6.0. Their scope,
provenance, and evaluation limitations are documented in
[`docs/static-identifier-mappings.md`](docs/static-identifier-mappings.md).

Subsystem evidence can be disabled for inference evaluation:

```bash
semgem build path/to/model.xml \
    --out outputs/no_subsystem_evidence.sqlite \
    --ignore-subsystems \
    --no-kegg
```

This preserves subsystem data in the raw model tables but prevents the
evidence engine from using those labels when generating conclusions.

Directory discovery accepts `.xml`, `.xml.gz`, `.sbml`, and `.sbml.gz` files,
ignores unrelated files, sorts the discovered paths, and avoids importing the
same file twice when inputs overlap. Files and directories can be mixed in the
same command.

SemGEM rejects an exact duplicate model. It also rejects reuse of an existing SBML model ID with different file content. Differently identified models with identical hashes are allowed with a warning.

## Querying a semantic catalog

```python
from semgem.query import SemanticCatalog

with SemanticCatalog("outputs/semantic_catalog.sqlite") as catalog:
    models = catalog.list_models()
    reaction = catalog.get_entity("iJO1366", "reaction", "ATPM")
    annotations = catalog.get_annotations("iJO1366", "reaction", "ATPM")
    concepts = catalog.get_concepts("iJO1366", "reaction", "ATPM")
```

Entity queries always include the model ID because different models may reuse
the same reaction, metabolite, or gene identifier. `explain_concept()` returns
the fixed evidence codes, sources, observed values, explanations, and weights supporting an
assignment. The query connection is read-only.

The same read-only operations are available from the command line:

```bash
semgem models outputs/semantic_catalog.sqlite

semgem search outputs/semantic_catalog.sqlite ATPM --type reaction

semgem entity outputs/semantic_catalog.sqlite \
    --model iJO1366 --type reaction --id ATPM

semgem annotations outputs/semantic_catalog.sqlite \
    --model iJO1366 --type reaction --id ATPM

semgem concepts outputs/semantic_catalog.sqlite \
    --model iJO1366 --type reaction --id ATPM

semgem explain outputs/semantic_catalog.sqlite \
    --model iJO1366 --type reaction --id BIOMASS_Ec_iJO1366_core_53p95M \
    --concept objective:biomass_production
```

`search` performs a case-insensitive substring search across entity IDs, names,
annotation identifiers, and semantic concepts. Results include the matching
field and source. Use `--model`, `--type`, `--source`, and `--limit` to narrow
cross-model results.

## Testing

```bash
pytest
```

The current suite covers extraction, canonical label normalization, fixed
evidence generation, scoring, SBO hierarchy parsing, KEGG response parsing,
MetaNetX/Rhea cross-reference parsing, static transport inference, provider
caching, relational insertion,
annotation normalization, duplicate detection, rollback, deletion, entity-type
validation, and file hashing.

## Architecture

```text
SBML model
    ↓
COBRApy loader
    ↓
typed extraction records
    ↓
raw model baseline
    ↓
SBO / optional MetaNetX and Rhea identity resolution
    ↓
optional batched KEGG pathway resolution
    ↓
fixed candidate evidence
    ↓
configurable provisional scoring
    ↓
multi-model SQLite semantic catalog
```

All reactions, metabolites, and genes receive a shared internal entity identity. Their original SBML identifiers are preserved. Type-specific tables store reaction, metabolite, and gene details, while annotations and semantic concepts reference the shared entity.

See [docs/database-schema.md](docs/database-schema.md) for the relational design.

## Evidence rules

Canonical concepts are stored in:

```text
semgem/resources/concepts.toml
```

Fixed evidence templates, generation rules, provisional weights, and
thresholds are stored in:

```text
semgem/resources/evidence_rules.toml
```

The Python evidence engine applies these definitions without embedding static
KEGG identifier mappings. Current weights and thresholds are explicitly
provisional and have not yet been biologically calibrated.

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
- [External enrichment design](docs/enrichment-design.md)
- [Provisional concept inventory and smoke evaluation](docs/concept-inventory.md)
- [Provisional biological and multi-model evaluation](docs/evaluation-report.md)
- [Experimental exact reaction-ID mappings](docs/static-identifier-mappings.md)
- [Future work](docs/future_work.md)
- [Living TODO list](docs/todo.md)
- [External data-source contact plan](docs/data-source-contacts.md)

## Current limitations

- The expanded reaction-level concept vocabulary remains provisional and has
  not yet undergone the thesis-scale biological evaluation.
- Confidence scores use simple additive rule weights and are not calibrated probabilities.
- KEGG pathway coverage depends on usable reaction identities, network access,
  and KEGG availability. MetaNetX/Rhea can bridge more reaction identities,
  but models without identity annotations still cannot be pathway-enriched.
- Dedicated pathway listing/filtering commands are not yet implemented;
  canonical pathway concepts remain searchable through existing queries.
- The current SQLite schema is regenerated during development; schema migrations are not supported.
- Databases generated with the earlier prototype schema must be rebuilt from their source model files.
- External resource licensing and redistribution requirements must be considered before publishing enriched datasets.
