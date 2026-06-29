CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT,
    model_name TEXT,
    source_file TEXT
);

CREATE TABLE IF NOT EXISTS reactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id INTEGER,
    reaction_id TEXT,
    name TEXT,
    lower_bound REAL,
    upper_bound REAL,
    objective_coefficient REAL,
    subsystem TEXT,
    gene_reaction_rule TEXT,
    equation TEXT,
    FOREIGN KEY (model_id) REFERENCES models(id)
);

CREATE TABLE IF NOT EXISTS metabolites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id INTEGER,
    metabolite_id TEXT,
    name TEXT,
    compartment TEXT,
    formula TEXT,
    charge INTEGER,
    FOREIGN KEY (model_id) REFERENCES models(id)
);

CREATE TABLE IF NOT EXISTS reaction_metabolites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reaction_id TEXT,
    metabolite_id TEXT,
    coefficient REAL
);

CREATE TABLE IF NOT EXISTS annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_entity_type TEXT,
    model_entity_id TEXT,
    annotation_key TEXT,
    annotation_value TEXT
);