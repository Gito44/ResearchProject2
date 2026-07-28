# SemGEM TODO

This is a living list of work that has been intentionally postponed. Add items here whenever a design discussion concludes that something may be useful later but is not required immediately.

## External data access

- [ ] Review and send the enquiries in `docs/data-source-contacts.md`.
- [ ] Record replies and any conditions in the response table.
- [x] Record the KEGG correspondence and define the current academic,
  local-use decision.
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

## Deferred programming and scalability work

- [ ] **High priority:** prevent cycles and repeated path expansion in the
  recursive external-term relationship query before supporting more complex
  relationship graphs.
- [ ] **High priority for large catalogs:** process annotations, entities,
  external evidence, candidates, and conclusions in batches instead of loading
  the complete catalog into memory.
- [ ] Consider SQLite staging tables for candidate evidence if batching becomes
  necessary; avoid introducing duplicate JSON/CSV cache formats unless portable
  pipeline checkpoints become a requirement.
- [ ] Benchmark model import and replace high-volume per-row SQL operations with
  batched inserts or cached identifier lookups where this materially improves
  performance.
- [ ] Decide whether a multi-model build should be atomic for the whole command
  or explicitly retain and report successfully imported models when a later
  model fails.
- [ ] Split the growing `SemanticDatabase` class into smaller model,
  enrichment, and semantic repositories when its responsibilities begin to
  impede maintenance.
- [ ] Strengthen type annotations at component boundaries and consider database
  protocols for the pipeline and enrichment providers.
- [ ] Add automated formatting, linting, static type checking, and coverage
  reporting to the development toolchain.
- [ ] Remove `pandas` from runtime dependencies unless a planned feature begins
  using it.
- [ ] Consider SQLite FTS5 if substring search becomes too slow on large
  multi-model catalogs.

## Deferred gene support

- [ ] Extend the minimal `genes` table when useful gene-specific fields are identified.
- [ ] Decide whether any gene state, function, product, locus, or sequence metadata belongs in SemGEM rather than only in annotations.
- [ ] Avoid treating COBRApy's temporary `gene.functional` state as permanent source-model semantics without an explicit design decision.
- [ ] Parse gene-reaction rules into a structured Boolean representation if downstream queries need to distinguish `AND` and `OR` relationships beyond the stored rule text.

## Deferred semantic and enrichment work

- [x] Implement the configurable evidence-engine foundation.
- [x] Implement shared external-term, relationship-provenance, and
  enrichment-run storage.
- [x] Review the normalized dynamic-evidence contract before implementing
  provider evidence generation.
- [x] Review evidence weighting and confidence calculation before replacing the
  current prototype scoring behavior.
- [ ] Complete the biological concept rule set after external enrichment data
  and provenance are available.
- [x] Expand the provisional v0.5 reaction types, exchange concepts, and
  pathway vocabulary using the inspected SBO terms and model subsystems.
- [x] Implement SBO enrichment as a required v1 provider.
- [x] Implement optional KEGG REST enrichment as a required v1 provider.
- [ ] Biologically calibrate the provisional v0.5 evidence weights, concept
  thresholds, labels, and synonyms before v1.
- [ ] Test unresolved-identifier rates before defining warning thresholds.
- [ ] Evaluate MetaNetX enrichment as a v1 stretch goal.
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

## Thesis evaluation

- [x] Create a reproducible 118-pair manually curated development benchmark
  with precision, recall, F1, and Wilson confidence intervals.
- [x] Run a provisional 16-model, 37,017-reaction offline cohort evaluation
  and record coverage, runtime, annotation availability, and pathway depth.
- [x] Compare the curated benchmark against a portable exact-label baseline
  and quantify the reduction in model-specific alias handling.
- [x] Run threshold sensitivity analysis and retain 0.75 on the observed stable
  plateau; record that KEGG reference-map scope cannot be corrected by weight
  changes alone.
- [ ] Obtain independent biological review of the curated benchmark and expand
  its predeclared positive and negative examples before final thesis reporting.
- [ ] Compare the same model set under different semantic evidence modes:
  model-only, default redistributable enrichment, and default enrichment plus
  KEGG.
- [ ] Measure and compare reaction/pathway coverage, agreement between sources,
  false positives, false negatives, unresolved entities, and enrichment runtime.
- [ ] Report cases where KEGG adds useful classifications, changes an existing
  classification, or disagrees with model-local or other external evidence.
- [ ] Evaluate whether the additional KEGG coverage justifies its network,
  runtime, licensing, and reproducibility trade-offs.

## Deferred knowledgebase and application work

- [ ] Build a large multi-model knowledgebase after the package and schema have been evaluated on a controlled model set.
- [ ] Add cross-model pathway and annotation comparison features.
- [ ] Add a web browser or dashboard for models, entities, pathways, and evidence.
- [ ] Add a REST, GraphQL, or SPARQL service if non-Python applications need remote access.
- [ ] Integrate the semantic catalog with the original FBA web application.
- [ ] Add pathway and evidence visualizations.

## Post-v1 provider investigation

- [ ] Evaluate whether BiGG and Escher maps provide sufficiently reliable,
  redistributable pathway evidence to justify dedicated providers.
- [ ] Evaluate Rhea as an additional curated reaction-identity provider after
  the SBO/KEGG v1 workflow is complete.

## Deployment and licensing

- [ ] Define how KEGG-derived data can be cached, exported, and redistributed under applicable usage terms.
- [ ] Investigate alternative redistributable resources for non-academic or commercial deployments.
- [ ] Add licence and provenance metadata before publishing a shared enriched-model catalog.
