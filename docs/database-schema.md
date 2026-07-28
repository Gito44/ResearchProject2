# Database schema

## Design goals

The SemGEM SQLite catalog is designed to:

- store one or many SBML models;
- preserve original model identifiers;
- give every reaction, metabolite, and gene a unique internal identity;
- support shared annotations and semantic concepts across entity types;
- enforce relational integrity and cascading deletion; and
- import each model atomically.

## Model identity

`models.id` is the database-local model key. `models.original_id` preserves the
SBML model ID. A SHA-256 hash of the source file supports exact duplicate and
identity-conflict detection. `models.compartments_json` preserves the model's
mapping from compartment identifiers to readable names so static inference can
distinguish mitochondrial, chloroplast, extracellular, and other transport.

The current behavior is:

| Situation | Result |
|---|---|
| Same model ID and same file hash | Reject as already imported |
| Same model ID and different file hash | Reject as an identity conflict |
| Different model ID and same file hash | Warn and import separately |
| Different model ID and different file hash | Import normally |

Canonical semantic fingerprints, aliases, and explicit model versions are deferred.

## Shared entities

The `entities` table is the source of internal IDs for all supported model entity types:

```text
entities
├── reaction → reactions
├── metabolite → metabolites
└── gene → genes
```

The combination `(model_id, entity_type, original_id)` is unique. This allows different models to reuse conventional identifiers such as `ATPM` while preventing duplicate entities of the same type within one model.

Numeric entity IDs are internal database keys, not permanent public identifiers. Stable UUIDs may be added later if cross-database merging becomes necessary.

## Type-specific records

- `reactions` stores bounds, objective coefficients, subsystem text, gene-reaction rules, and equations.
- `metabolites` stores compartment, formula, and charge.
- `genes` is deliberately minimal and can be extended when useful gene-specific fields are identified.

The Python database layer validates that type-specific records reference an entity of the correct type. SQL triggers are deferred as possible hardening for external database writers.

## Relationships

`reaction_metabolites` represents many-to-many stoichiometric relationships and stores the coefficient belonging to each reaction/metabolite pair.

`reaction_genes` represents reaction/gene membership. The original Boolean `AND`/`OR` structure remains preserved in `reactions.gene_reaction_rule`; structured Boolean parsing is deferred.

## Annotations

Each annotation identifier is stored as an individual row:

```text
entity_id | source        | identifier
----------|---------------|-----------
101       | kegg.reaction | R00703
101       | rhea          | 23447
101       | rhea          | 23445
```

This is intentionally normalized instead of storing list values as JSON, allowing direct source/identifier queries.

## External enrichment

Source-model annotations remain separate from information added by SemGEM.
The enrichment storage layer contains:

```text
external_terms
├── external_term_relationships
│   └── provider_relationship_evidence
└── enrichment_assertions
    └── entity_assertion_evidence

enrichment_runs
```

`external_terms` stores catalog-wide identifiers from established resources.
The combination `(source, identifier)` is unique, so a term such as
`SBO:0000629` is stored once even when it is used by many models.

`external_term_relationships` stores only provider relationships relevant to
the annotations present in catalog models. For example:

```text
KEGG:R00771 → belongs_to_pathway → KEGG:map00010
```

This shared relationship acts as a cross-model cache: models that reuse
`R00771` can reuse the relationship without another provider request.
`provider_relationship_evidence` records the provider, method, resource
version, retrieval time, and run that supplied the relationship.

`enrichment_assertions` connects a model-local entity to a shared external
term:

```text
BIOMASS_TEST → has_sbo_term → SBO:0000629
```

`entity_assertion_evidence` records why an entity assertion exists, including its
provider, evidence type, originating model annotation when applicable,
supporting external relationship, retrieval method, external resource version,
retrieval time, and additional details. Evidence is separate because one
assertion may have support from multiple sources.

`enrichment_runs` records whether a provider execution completed, partially
completed, or failed, together with requested, resolved, and unresolved counts.
This prevents an incomplete network enrichment from appearing complete.

Deleting a model removes its model-specific assertions and evidence. Shared
external terms, provider relationships, relationship provenance, and run
records remain available because other models may use them. Re-running an
identical assertion refreshes evidence from the provider being rerun instead
of creating duplicate records; evidence from other providers is preserved.

## Semantic concepts and evidence

`semantic_concepts` assigns a named concept and confidence score to a shared entity. One current result is stored per entity/concept pair.

`concept_evidence` records:

- fixed evidence code and source;
- observed runtime value;
- human-readable explanation;
- annotation/assertion/relationship provenance where applicable; and
- rule weight.

This supports transparent inspection of why a concept was assigned.

## Transactions and deletion

Every complete model import runs in one transaction. An error rolls back the model and all rows inserted during that import.

Foreign keys use `ON DELETE CASCADE`, so deleting a model removes its entities, type-specific data, relationships, annotations, concepts, and evidence. SQLite foreign-key enforcement is explicitly enabled for every connection.

## Deferred database work

The current schema intentionally postpones:

- performance indexes based on measured query patterns;
- UUIDs and public display identifiers;
- model aliases and shared content storage;
- canonical model fingerprints and version relationships;
- extended provenance;
- SQL triggers for subtype enforcement; and
- database backends other than SQLite.

These decisions are tracked in [todo.md](todo.md) and discussed in [future_work.md](future_work.md).
