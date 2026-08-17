PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_id TEXT NOT NULL UNIQUE,
    name TEXT,
    source_file TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    compartments_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS catalog_metadata (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id INTEGER NOT NULL,
    entity_type TEXT NOT NULL,
    original_id TEXT NOT NULL,
    name TEXT,
    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE CASCADE,
    UNIQUE (model_id, entity_type, original_id),
    CHECK (entity_type IN ('reaction', 'metabolite', 'gene'))
);

CREATE TABLE IF NOT EXISTS reactions (
    entity_id INTEGER PRIMARY KEY,
    lower_bound REAL NOT NULL,
    upper_bound REAL NOT NULL,
    objective_coefficient REAL NOT NULL DEFAULT 0.0,
    subsystem TEXT,
    gene_reaction_rule TEXT,
    equation TEXT,
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS metabolites (
    entity_id INTEGER PRIMARY KEY,
    compartment TEXT,
    compartment_free_id TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    formula TEXT,
    charge INTEGER,
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS genes (
    entity_id INTEGER PRIMARY KEY,
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reaction_metabolites (
    reaction_entity_id INTEGER NOT NULL,
    metabolite_entity_id INTEGER NOT NULL,
    coefficient REAL NOT NULL,
    PRIMARY KEY (reaction_entity_id, metabolite_entity_id),
    FOREIGN KEY (reaction_entity_id) REFERENCES reactions(entity_id) ON DELETE CASCADE,
    FOREIGN KEY (metabolite_entity_id) REFERENCES metabolites(entity_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reaction_genes (
    reaction_entity_id INTEGER NOT NULL,
    gene_entity_id INTEGER NOT NULL,
    PRIMARY KEY (reaction_entity_id, gene_entity_id),
    FOREIGN KEY (reaction_entity_id) REFERENCES reactions(entity_id) ON DELETE CASCADE,
    FOREIGN KEY (gene_entity_id) REFERENCES genes(entity_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    identifier TEXT NOT NULL,
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    UNIQUE (entity_id, source, identifier)
);

CREATE TABLE IF NOT EXISTS external_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    identifier TEXT NOT NULL,
    term_type TEXT NOT NULL,
    name TEXT,
    description TEXT,
    source_version TEXT,
    is_obsolete INTEGER NOT NULL DEFAULT 0,
    UNIQUE (source, identifier),
    CHECK (is_obsolete IN (0, 1))
);

CREATE TABLE IF NOT EXISTS external_term_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_term_id INTEGER NOT NULL,
    predicate TEXT NOT NULL,
    object_term_id INTEGER NOT NULL,
    FOREIGN KEY (subject_term_id) REFERENCES external_terms(id) ON DELETE CASCADE,
    FOREIGN KEY (object_term_id) REFERENCES external_terms(id) ON DELETE CASCADE,
    UNIQUE (subject_term_id, predicate, object_term_id)
);

CREATE TABLE IF NOT EXISTS enrichment_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    resource_version TEXT,
    requested_count INTEGER NOT NULL DEFAULT 0,
    resolved_count INTEGER NOT NULL DEFAULT 0,
    unresolved_count INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT,
    CHECK (status IN ('running', 'completed', 'partial', 'failed')),
    CHECK (requested_count >= 0),
    CHECK (resolved_count >= 0),
    CHECK (unresolved_count >= 0)
);

CREATE TABLE IF NOT EXISTS provider_relationship_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relationship_id INTEGER NOT NULL,
    run_id INTEGER,
    provider TEXT NOT NULL,
    retrieval_method TEXT NOT NULL,
    source_identifier TEXT,
    resource_version TEXT,
    retrieved_at TEXT,
    details TEXT,
    FOREIGN KEY (relationship_id)
        REFERENCES external_term_relationships(id) ON DELETE CASCADE,
    FOREIGN KEY (run_id) REFERENCES enrichment_runs(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS enrichment_assertions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL,
    predicate TEXT NOT NULL,
    external_term_id INTEGER NOT NULL,
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    FOREIGN KEY (external_term_id) REFERENCES external_terms(id) ON DELETE CASCADE,
    UNIQUE (entity_id, predicate, external_term_id)
);

CREATE TABLE IF NOT EXISTS entity_assertion_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assertion_id INTEGER NOT NULL,
    relationship_id INTEGER,
    run_id INTEGER,
    provider TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    source_annotation_id INTEGER,
    source_identifier TEXT,
    retrieval_method TEXT NOT NULL,
    resource_version TEXT,
    retrieved_at TEXT,
    details TEXT,
    FOREIGN KEY (assertion_id) REFERENCES enrichment_assertions(id) ON DELETE CASCADE,
    FOREIGN KEY (relationship_id)
        REFERENCES external_term_relationships(id) ON DELETE SET NULL,
    FOREIGN KEY (run_id) REFERENCES enrichment_runs(id) ON DELETE SET NULL,
    FOREIGN KEY (source_annotation_id) REFERENCES annotations(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS semantic_concepts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL,
    concept_name TEXT NOT NULL,
    preferred_label TEXT NOT NULL,
    confidence REAL NOT NULL,
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    UNIQUE (entity_id, concept_name),
    CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

CREATE TABLE IF NOT EXISTS concept_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concept_id INTEGER NOT NULL,
    evidence_code TEXT NOT NULL,
    source TEXT NOT NULL,
    explanation TEXT NOT NULL,
    observed_value TEXT,
    weight REAL NOT NULL,
    annotation_id INTEGER,
    assertion_id INTEGER,
    relationship_id INTEGER,
    FOREIGN KEY (concept_id) REFERENCES semantic_concepts(id) ON DELETE CASCADE,
    FOREIGN KEY (annotation_id) REFERENCES annotations(id) ON DELETE SET NULL,
    FOREIGN KEY (assertion_id) REFERENCES enrichment_assertions(id) ON DELETE SET NULL,
    FOREIGN KEY (relationship_id)
        REFERENCES external_term_relationships(id) ON DELETE SET NULL,
    CHECK (weight >= 0.0 AND weight <= 1.0)
);

PRAGMA user_version = 6;
