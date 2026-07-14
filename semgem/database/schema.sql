PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_id TEXT NOT NULL UNIQUE,
    name TEXT,
    source_file TEXT NOT NULL,
    content_hash TEXT NOT NULL
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

CREATE TABLE IF NOT EXISTS semantic_concepts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL,
    concept_name TEXT NOT NULL,
    confidence REAL NOT NULL,
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    UNIQUE (entity_id, concept_name),
    CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

CREATE TABLE IF NOT EXISTS concept_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concept_id INTEGER NOT NULL,
    evidence_type TEXT NOT NULL,
    target_field TEXT NOT NULL,
    matched_value TEXT,
    evidence_text TEXT NOT NULL,
    weight REAL NOT NULL,
    FOREIGN KEY (concept_id) REFERENCES semantic_concepts(id) ON DELETE CASCADE,
    CHECK (weight >= 0.0 AND weight <= 1.0)
);

PRAGMA user_version = 1;
