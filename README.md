# SemGEM

SemGEM is a research prototype that generates an explainable semantic layer over SBML genome-scale metabolic models (GEMs).

Equivalent biological features are often represented differently across GEMs: identifiers, names, subsystem labels, annotations, and compartment conventions vary between models. SemGEM combines those model-local facts with established external resources and stores consistent semantic assignments in a queryable multi-model catalog.

Version **0.11.1** contains the implementation frozen for MSc thesis evaluation plus public-documentation corrections. It is intended to save scientists and developers time when exploring heterogeneous model collections; it is not a source of definitive biological truth or a replacement for model curation.

## What SemGEM provides

- SBML import through COBRApy.
- One SQLite catalog containing multiple models.
- Reactions, metabolites, genes, stoichiometry, annotations, and gene associations.
- Default SBO, MetaNetX, and Rhea enrichment using a managed local resource cache.
- Optional runtime KEGG pathway enrichment.
- Evidence-backed pathway and functional classifications with confidence scores.
- Cross-model search, coverage summaries, entity inspection, and evidence explanations.
- Portable JSON and gzip-compressed JSON export.

## Installation

SemGEM requires Python 3.11 or later. Until a PyPI release is available, install the frozen GitHub release in a virtual environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "git+https://github.com/Gito44/ResearchProject2.git@v0.11.1"
```

Confirm the installation:

```bash
semgem --help
```

For local development:

```bash
git clone git@github.com:Gito44/ResearchProject2.git
cd ResearchProject2
git switch --detach v0.11.1
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
pytest
```

## Quick start

Build a catalog from one model, several models, or a directory containing SBML files:

```bash
semgem build path/to/models/ --out semantic_catalog.sqlite --no-kegg
```

SBO, MetaNetX, and Rhea enrichment run by default. Missing official resources are downloaded to `~/.semgem/resources`, verified, and reused on later runs.

KEGG is recommended when pathway enrichment is needed, but it requires internet access and takes longer:

```bash
semgem build path/to/models/ --out semantic_catalog.sqlite --kegg
```

SemGEM does not distribute static KEGG mappings. KEGG-derived results remain in the user's local catalog, and users are responsible for following KEGG's terms.

Inspect the result:

```bash
semgem summary semantic_catalog.sqlite
semgem coverage semantic_catalog.sqlite
semgem search semantic_catalog.sqlite glycolysis --type reaction
```

Export compact compressed JSON:

```bash
semgem export semantic_catalog.sqlite \
  --out semantic_catalog.json.gz \
  --compact
```

See the [CLI reference](docs/cli-reference.md) for all commands and common workflows.

## Python queries

```python
from semgem.query import SemanticCatalog

with SemanticCatalog("semantic_catalog.sqlite") as catalog:
    models = catalog.list_models()
    reaction = catalog.get_entity("iJO1366", "reaction", "ATPM")
    concepts = catalog.get_concepts("iJO1366", "reaction", "ATPM")
```

Entity queries include the model ID because local identifiers can be reused by different models.

## Output and provenance

The SQLite catalog preserves original model data separately from enriched assertions, semantic conclusions, and their supporting evidence. Provider versions, retrieval details, observed values, rule weights, and confidence scores are retained where applicable. See the [database schema](docs/database-schema.md) for the relational structure.

JSON exports use a versioned, model-independent structure suitable for downstream applications. Use `--model` to select models, `--no-evidence` to omit evidence records, and `--gzip` or a `.gz` suffix for compression.

## Important limitations

- Semantic assignments are aids for exploration and software development, not validated biological annotations.
- The concept vocabulary, rules, thresholds, and weights remain provisional pending broader biological curation.
- Provider coverage depends on the identifiers and annotations available in each source model.
- KEGG enrichment depends on network availability and KEGG usage conditions.
- Schema migrations are not supported; catalogs made by older prototypes should be rebuilt from the source SBML files.

## Documentation

- [CLI reference](docs/cli-reference.md)
- [Database schema](docs/database-schema.md)
- [Software and data-source licensing](docs/licensing.md)

## Licensing status

No general software licence has yet been granted for SemGEM. The repository is publicly available for inspection and installation, but permission to modify or redistribute the source code has not yet been defined. External resources retain their own licences and terms; see the [licensing notes](docs/licensing.md).
