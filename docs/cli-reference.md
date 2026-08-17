# SemGEM CLI reference

Run `semgem --help` to list commands and `semgem COMMAND --help` for the authoritative options supported by the installed version.

## Build a catalog

```bash
semgem build MODEL_PATHS... --out CATALOG.sqlite [OPTIONS]
```

`MODEL_PATHS` may contain individual SBML files, directories, or both. Directories are searched recursively for `.xml`, `.xml.gz`, `.sbml`, and `.sbml.gz` files. Multiple models are stored in one SQLite catalog.

Common options:

| Option | Purpose |
|---|---|
| `--out`, `-o` | Catalog to create or extend. |
| `--kegg` / `--no-kegg` | Enable or disable optional online KEGG enrichment. |
| `--metanetx` / `--no-metanetx` | Control MetaNetX reaction-identity enrichment. Enabled by default. |
| `--rhea` / `--no-rhea` | Control Rhea enrichment. Enabled by default. |
| `--metanetx-chemistry` | Enable experimental metabolite chemistry and stoichiometric enrichment; requires a large download. |
| `--resource-dir PATH` | Override the managed provider-resource directory. |
| `--refresh-resources` | Download fresh copies of enabled managed resources. |
| `--offline` | Prohibit downloads and require verified cached resources. |
| `--ignore-subsystems` | Preserve subsystem fields but exclude them as classification evidence. |

Examples:

```bash
# Default offline-provider workflow, without KEGG
semgem build models/ --out semantic_catalog.sqlite --no-kegg

# Full normal workflow including online KEGG enrichment
semgem build models/ --out semantic_catalog.sqlite --kegg

# Controlled run using an existing verified cache only
semgem build models/ --out semantic_catalog.sqlite --offline --no-kegg
```

## Inspect managed resources

```bash
semgem resources
semgem resources --format json
```

The default cache is `~/.semgem/resources`. It can also be changed with `SEMGEM_RESOURCE_DIR`.

## Catalog overview

```bash
semgem models CATALOG.sqlite
semgem summary CATALOG.sqlite [--model MODEL_ID]
semgem coverage CATALOG.sqlite [--model MODEL_ID]
semgem providers CATALOG.sqlite
semgem compare CATALOG.sqlite --model MODEL_A --model MODEL_B
```

`coverage` distinguishes pathway assignments, other actionable functional assignments, generic-only assignments, and unclassified reactions. Add `--format json` to analysis commands when using their output in scripts.

## Search and classification queries

```bash
semgem search CATALOG.sqlite QUERY [OPTIONS]
semgem get-concept CATALOG.sqlite --concept CONCEPT [OPTIONS]
semgem unclassified CATALOG.sqlite [OPTIONS]
```

Search can be limited using:

- `--model MODEL_ID`
- `--type reaction|metabolite|gene`
- `--source PROVIDER`
- `--limit NUMBER`

Example:

```bash
semgem search semantic_catalog.sqlite glycolysis --type reaction
semgem get-concept semantic_catalog.sqlite \
  --concept pathway:glycolysis_gluconeogenesis \
  --model e_coli_core
```

## Inspect one entity

Entity-specific commands require the model, entity type, and original model-local identifier:

```bash
semgem entity CATALOG.sqlite --model MODEL --type TYPE --id ID
semgem annotations CATALOG.sqlite --model MODEL --type TYPE --id ID
semgem concepts CATALOG.sqlite --model MODEL --type TYPE --id ID
```

Explain one accepted assignment and its evidence:

```bash
semgem explain CATALOG.sqlite \
  --model MODEL \
  --type reaction \
  --id REACTION_ID \
  --concept CONCEPT_ID
```

## JSON export

```bash
semgem export CATALOG.sqlite --out semantic_catalog.json
```

Options:

| Option | Purpose |
|---|---|
| `--model`, `-m` | Export only a selected model; repeat for several models. |
| `--no-evidence` | Omit detailed evidence records. |
| `--compact` | Remove indentation and unnecessary whitespace. |
| `--gzip` | Compress the output; a `.gz` suffix enables this automatically. |

Recommended compact export:

```bash
semgem export semantic_catalog.sqlite \
  --out semantic_catalog.json.gz \
  --compact
```

## Getting help

```bash
semgem --help
semgem build --help
semgem search --help
semgem export --help
```
