# SemGEM TODO

This is a living list of work that has been intentionally postponed. Add items here whenever a design discussion concludes that something may be useful later but is not required immediately.

## External data access

- [ ] Review and send the enquiries in `docs/data-source-contacts.md`.
- [ ] Record replies and any conditions in the response table.
- [ ] Convert confirmed conditions into source-specific attribution, caching,
  provenance and redistribution requirements before enrichment is released.

## Deferred database and identity work

- [ ] Add stable UUIDs for entities if cross-database merging, public APIs, or published semantic records are implemented.
- [ ] Consider type-prefixed display identifiers such as `R101`, `M102`, and `G103` after inspecting real query output.
- [ ] Consider SQLite triggers that enforce agreement between `entities.entity_type` and type-specific tables if programs are later allowed to write directly to the database; the current package will enforce this in Python and test it.
- [ ] Add canonical model fingerprints that ignore irrelevant XML formatting and selected metadata.
- [ ] Add explicit model-version relationships.
- [ ] Add aliases for differently named but equivalent models.
- [ ] Reuse stored entities and semantic content for equivalent models instead of importing duplicate rows.
- [ ] Add extended model provenance, including source URI, publication, licence, authors, taxonomy, and import timestamp.
- [ ] Add performance indexes after real query patterns and larger catalogs can be benchmarked.
- [ ] Investigate PostgreSQL or another server database if concurrent access or substantially larger catalogs are required.

## Deferred gene support

- [ ] Extend the minimal `genes` table when useful gene-specific fields are identified.
- [ ] Decide whether any gene state, function, product, locus, or sequence metadata belongs in SemGEM rather than only in annotations.
- [ ] Avoid treating COBRApy's temporary `gene.functional` state as permanent source-model semantics without an explicit design decision.
- [ ] Parse gene-reaction rules into a structured Boolean representation if downstream queries need to distinguish `AND` and `OR` relationships beyond the stored rule text.

## Deferred semantic and enrichment work

- [ ] Add CLI annotation filtering by source, for example
  `semgem annotations ... --source kegg.reaction`, to keep heavily annotated
  entities readable.
- [ ] Support additional pathway and ontology resources beyond the initial SBO and KEGG scope.
- [ ] Add MetaNetX-based cross-reference enrichment.
- [ ] Investigate BiGG/Escher maps as pathway evidence for models without subsystem or KEGG annotations.
- [ ] Preserve and expose disagreements between model-local groups and external pathway resources.
- [ ] Add configurable semantic policies such as model-only, KEGG-only, consensus, strict, and permissive results.
- [ ] Replace simple additive evidence weights with a better validated confidence model if evaluation shows it is necessary.
- [ ] Add negative and conflicting evidence.
- [ ] Investigate annotation suggestions and optional export of proposed SBML Groups.

## Deferred knowledgebase and application work

- [ ] Build a large multi-model knowledgebase after the package and schema have been evaluated on a controlled model set.
- [ ] Add cross-model pathway and annotation comparison features.
- [ ] Add a web browser or dashboard for models, entities, pathways, and evidence.
- [ ] Add a REST, GraphQL, or SPARQL service if non-Python applications need remote access.
- [ ] Integrate the semantic catalog with the original FBA web application.
- [ ] Add pathway and evidence visualizations.

## Deployment and licensing

- [ ] Define how KEGG-derived data can be cached, exported, and redistributed under applicable usage terms.
- [ ] Investigate alternative redistributable resources for non-academic or commercial deployments.
- [ ] Add licence and provenance metadata before publishing a shared enriched-model catalog.
