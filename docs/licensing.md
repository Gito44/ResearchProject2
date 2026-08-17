# Software and data-source licensing

## SemGEM source code

No general software licence has yet been selected or granted for SemGEM. The repository is publicly available for inspection and installation, but the absence of a software licence does not grant permission to modify or redistribute its source code.

The licensing position will be reviewed with the project supervisor and the University of Manchester before a broader software release.

## External resources

SemGEM preserves provider provenance and does not replace the terms of any external resource. Users are responsible for checking the current terms that apply to their use and any redistribution of enriched outputs.

### Systems Biology Ontology

SemGEM distributes an SBO snapshot with its associated licence and notice. See:

- `semgem/resources/sbo/LICENSE`
- `semgem/resources/sbo/NOTICE.md`

### Rhea

Rhea data is published under CC BY 4.0. Attribution and the applicable provider terms must be retained when required.

### MetaNetX

MetaNetX resources are generally made available under CC BY 4.0, while cross-referenced records can retain restrictions imposed by their original sources. Users should preserve provenance and review the applicable upstream terms before redistributing enriched catalogs.

### KEGG

SemGEM does not distribute a static KEGG dataset or mappings. When explicitly enabled with `--kegg`, relationships are requested at runtime and stored in the user's local catalog. Accessing KEGG through SemGEM does not remove KEGG's usage or redistribution conditions. Users remain responsible for complying with the current KEGG terms and for citing the relevant KEGG publications in research outputs.

## Local generated catalogs

SQLite catalogs and JSON exports may combine facts from source SBML models and external providers. Their redistribution can therefore depend on the licences and terms of both the input models and the enabled providers.
