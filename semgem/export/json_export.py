"""Portable, versioned JSON export for local SemGEM catalogs."""

from __future__ import annotations

import gzip
import json
from collections import defaultdict
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from semgem.evidence.load_rules import load_concepts
from semgem.query import EntityNotFoundError, SemanticCatalog


FORMAT_NAME = "semgem-semantic-catalog"
FORMAT_VERSION = "1.0"


def package_version() -> str:
    try:
        return version("semgem")
    except PackageNotFoundError:
        return "unknown"


class JsonCatalogExporter:
    """Convert a SQLite semantic catalog into portable model-oriented JSON."""

    def __init__(self, catalog: SemanticCatalog, concepts_path: Path):
        self.catalog = catalog
        self.conn = catalog.conn
        schema_version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if schema_version != 6:
            raise ValueError(
                "JSON export requires SemGEM schema version 6; this catalog "
                f"uses version {schema_version}. Rebuild it from the source models."
            )
        self.concepts = load_concepts(concepts_path)

    def document(
        self,
        model_ids: list[str] | None = None,
        include_evidence: bool = True,
    ) -> dict:
        selected = self._selected_models(model_ids)
        return {
            "semgem": {
                "format": FORMAT_NAME,
                "schema_version": FORMAT_VERSION,
                "package_version": package_version(),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            "catalog": {
                "model_count": len(selected),
                "source_catalog": self.catalog.db_path.name,
                "metadata": self._catalog_metadata(),
            },
            "concept_definitions": {
                concept_id: {
                    "category": concept.category,
                    "label": concept.preferred_label,
                    "description": concept.description,
                    "synonyms": list(concept.synonyms),
                    "parents": list(concept.parents),
                }
                for concept_id, concept in sorted(self.concepts.items())
            },
            "provider_runs": [
                {
                    "provider": run.provider,
                    "status": run.status,
                    "resource_version": run.resource_version,
                    "requested": run.requested,
                    "resolved": run.resolved,
                    "unresolved": run.unresolved,
                    "started_at": run.started_at,
                    "completed_at": run.completed_at,
                    "error_summary": run.error_summary,
                }
                for run in self.catalog.list_provider_runs()
            ],
            "models": [
                self._model(model, include_evidence=include_evidence)
                for model in selected
            ],
        }

    def _catalog_metadata(self) -> dict:
        table_exists = self.conn.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'catalog_metadata'
            """
        ).fetchone()
        if table_exists is None:
            return {}
        return {
            row["key"]: json.loads(row["value_json"])
            for row in self.conn.execute(
                "SELECT key, value_json FROM catalog_metadata ORDER BY key"
            )
        }

    def write(
        self,
        output_path: Path,
        model_ids: list[str] | None = None,
        include_evidence: bool = True,
        compact: bool = False,
        compress: bool = False,
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = output_path.with_name(f".{output_path.name}.tmp")
        document = self.document(model_ids, include_evidence)
        try:
            opener = gzip.open if compress else open
            with opener(temporary_path, "wt", encoding="utf-8") as file:
                json.dump(
                    document,
                    file,
                    ensure_ascii=False,
                    indent=None if compact else 2,
                    separators=(",", ":") if compact else None,
                )
                file.write("\n")
            temporary_path.replace(output_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    def _selected_models(self, model_ids: list[str] | None):
        models = self.catalog.list_models()
        if model_ids is None:
            return models
        requested = list(dict.fromkeys(model_ids))
        by_id = {model.original_id: model for model in models}
        missing = [model_id for model_id in requested if model_id not in by_id]
        if missing:
            raise EntityNotFoundError(
                "Model not found: " + ", ".join(missing) + "."
            )
        return [by_id[model_id] for model_id in requested]

    def _model(self, model, include_evidence: bool) -> dict:
        compartments = self.conn.execute(
            "SELECT compartments_json FROM models WHERE id = ?",
            (model.internal_id,),
        ).fetchone()[0]
        entity_rows = self.conn.execute(
            """
            SELECT id, entity_type, original_id, name
            FROM entities
            WHERE model_id = ?
            ORDER BY entity_type, original_id
            """,
            (model.internal_id,),
        ).fetchall()
        annotations = self._annotations(model.internal_id)
        concepts = self._concepts(model.internal_id, include_evidence)
        reaction_properties = self._reaction_properties(model.internal_id)
        metabolite_properties = self._metabolite_properties(model.internal_id)
        reaction_metabolites = self._reaction_metabolites(model.internal_id)
        reaction_genes = self._reaction_genes(model.internal_id)

        output = {"reactions": [], "metabolites": [], "genes": []}
        for row in entity_rows:
            entity_id = row["id"]
            common = {
                "id": row["original_id"],
                "name": row["name"],
                "annotations": annotations.get(entity_id, []),
                "concepts": concepts.get(entity_id, []),
            }
            if row["entity_type"] == "reaction":
                common["properties"] = reaction_properties[entity_id]
                common["metabolites"] = reaction_metabolites.get(entity_id, [])
                common["genes"] = reaction_genes.get(entity_id, [])
                output["reactions"].append(common)
            elif row["entity_type"] == "metabolite":
                common["properties"] = metabolite_properties[entity_id]
                output["metabolites"].append(common)
            else:
                output["genes"].append(common)

        return {
            "id": model.original_id,
            "name": model.name,
            "source_file": model.source_file,
            "content_hash": model.content_hash,
            "compartments": json.loads(compartments),
            "entities": output,
        }

    def _annotations(self, model_id: int) -> dict[int, list[dict]]:
        grouped = defaultdict(list)
        for row in self.conn.execute(
            """
            SELECT a.entity_id, a.source, a.identifier
            FROM annotations AS a
            JOIN entities AS e ON e.id = a.entity_id
            WHERE e.model_id = ?
            ORDER BY a.entity_id, a.source, a.identifier
            """,
            (model_id,),
        ):
            grouped[row["entity_id"]].append(
                {"source": row["source"], "identifier": row["identifier"]}
            )
        return grouped

    def _concepts(
        self,
        model_id: int,
        include_evidence: bool,
    ) -> dict[int, list[dict]]:
        grouped = defaultdict(list)
        concept_rows = self.conn.execute(
            """
            SELECT c.id, c.entity_id, c.concept_name,
                   c.preferred_label, c.confidence
            FROM semantic_concepts AS c
            JOIN entities AS e ON e.id = c.entity_id
            WHERE e.model_id = ?
            ORDER BY c.entity_id, c.concept_name
            """,
            (model_id,),
        ).fetchall()
        evidence = self._evidence(model_id) if include_evidence else {}
        for row in concept_rows:
            item = {
                "id": row["concept_name"],
                "label": row["preferred_label"],
                "confidence": row["confidence"],
            }
            if include_evidence:
                item["evidence"] = evidence.get(row["id"], [])
            grouped[row["entity_id"]].append(item)
        return grouped

    def _evidence(self, model_id: int) -> dict[int, list[dict]]:
        grouped = defaultdict(list)
        rows = self.conn.execute(
            """
            SELECT ce.concept_id, ce.evidence_code, ce.source,
                   ce.observed_value, ce.explanation, ce.weight,
                   a.source AS annotation_source,
                   a.identifier AS annotation_identifier,
                   ea.predicate AS assertion_predicate,
                   et.source AS assertion_term_source,
                   et.identifier AS assertion_term_identifier,
                   et.name AS assertion_term_name
            FROM concept_evidence AS ce
            JOIN semantic_concepts AS sc ON sc.id = ce.concept_id
            JOIN entities AS e ON e.id = sc.entity_id
            LEFT JOIN annotations AS a ON a.id = ce.annotation_id
            LEFT JOIN enrichment_assertions AS ea ON ea.id = ce.assertion_id
            LEFT JOIN external_terms AS et ON et.id = ea.external_term_id
            WHERE e.model_id = ?
            ORDER BY ce.concept_id, ce.id
            """,
            (model_id,),
        ).fetchall()
        for row in rows:
            item = {
                "code": row["evidence_code"],
                "source": row["source"],
                "observed_value": row["observed_value"],
                "weight": row["weight"],
                "explanation": row["explanation"],
            }
            if row["annotation_source"] is not None:
                item["annotation"] = {
                    "source": row["annotation_source"],
                    "identifier": row["annotation_identifier"],
                }
            if row["assertion_predicate"] is not None:
                item["assertion"] = {
                    "predicate": row["assertion_predicate"],
                    "term": {
                        "source": row["assertion_term_source"],
                        "identifier": row["assertion_term_identifier"],
                        "name": row["assertion_term_name"],
                    },
                }
            grouped[row["concept_id"]].append(item)
        return grouped

    def _reaction_properties(self, model_id: int) -> dict[int, dict]:
        return {
            row["entity_id"]: {
                "lower_bound": row["lower_bound"],
                "upper_bound": row["upper_bound"],
                "objective_coefficient": row["objective_coefficient"],
                "subsystem": row["subsystem"],
                "gene_reaction_rule": row["gene_reaction_rule"],
                "equation": row["equation"],
            }
            for row in self.conn.execute(
                """
                SELECT r.* FROM reactions AS r
                JOIN entities AS e ON e.id = r.entity_id
                WHERE e.model_id = ?
                """,
                (model_id,),
            )
        }

    def _metabolite_properties(self, model_id: int) -> dict[int, dict]:
        return {
            row["entity_id"]: {
                "compartment": row["compartment"],
                "compartment_free_id": row["compartment_free_id"],
                "normalized_name": row["normalized_name"],
                "formula": row["formula"],
                "charge": row["charge"],
            }
            for row in self.conn.execute(
                """
                SELECT metabolite.* FROM metabolites AS metabolite
                JOIN entities AS e ON e.id = metabolite.entity_id
                WHERE e.model_id = ?
                """,
                (model_id,),
            )
        }

    def _reaction_metabolites(self, model_id: int) -> dict[int, list[dict]]:
        grouped = defaultdict(list)
        for row in self.conn.execute(
            """
            SELECT rm.reaction_entity_id, metabolite.original_id,
                   rm.coefficient
            FROM reaction_metabolites AS rm
            JOIN entities AS reaction ON reaction.id = rm.reaction_entity_id
            JOIN entities AS metabolite ON metabolite.id = rm.metabolite_entity_id
            WHERE reaction.model_id = ?
            ORDER BY rm.reaction_entity_id, metabolite.original_id
            """,
            (model_id,),
        ):
            grouped[row["reaction_entity_id"]].append(
                {"id": row["original_id"], "coefficient": row["coefficient"]}
            )
        return grouped

    def _reaction_genes(self, model_id: int) -> dict[int, list[str]]:
        grouped = defaultdict(list)
        for row in self.conn.execute(
            """
            SELECT rg.reaction_entity_id, gene.original_id
            FROM reaction_genes AS rg
            JOIN entities AS reaction ON reaction.id = rg.reaction_entity_id
            JOIN entities AS gene ON gene.id = rg.gene_entity_id
            WHERE reaction.model_id = ?
            ORDER BY rg.reaction_entity_id, gene.original_id
            """,
            (model_id,),
        ):
            grouped[row["reaction_entity_id"]].append(row["original_id"])
        return grouped
