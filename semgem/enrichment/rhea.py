from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from semgem.core.records import (
    AnnotationInputRecord,
    EnrichmentAssertionRecord,
    EnrichmentResult,
    EntityAssertionEvidenceRecord,
    ExternalTermRecord,
    ExternalTermRelationshipRecord,
    ProviderRelationshipEvidenceRecord,
)
from semgem.enrichment.base import EnrichmentProvider


class RheaProvider(EnrichmentProvider):
    """Resolve Rhea annotations and official reaction cross-references."""

    name = "rhea"
    annotation_sources = frozenset({"rhea"})
    resource_version = "Rhea TSV"
    _source_map = {
        "KEGG_REACTION": "kegg.reaction",
        "METACYC": "metacyc.reaction",
        "REACTOME": "reactome.reaction",
    }

    def __init__(self, xref_path: str | Path):
        self.xref_path = Path(xref_path)
        if not self.xref_path.is_file():
            raise FileNotFoundError(
                f"Rhea xref file not found: {self.xref_path}"
            )

    def enrich(
        self,
        annotations: Iterable[AnnotationInputRecord],
        run_id: int,
    ) -> EnrichmentResult:
        relevant = tuple(
            annotation
            for annotation in annotations
            if annotation.source in self.annotation_sources
        )
        requested = {
            self._normalize_identifier(annotation.identifier)
            for annotation in relevant
        }
        direction_to_master: dict[str, str] = {}
        rows = []
        with self.xref_path.open(encoding="utf-8") as file:
            header = next(file, "")
            if not header.startswith("RHEA_ID\t"):
                raise ValueError("Unexpected Rhea xref header.")
            for line in file:
                fields = line.rstrip("\n").split("\t")
                if len(fields) != 5:
                    continue
                rhea_id, _, master_id, xref_id, database = fields
                direction_to_master[rhea_id] = master_id
                rows.append((master_id, xref_id, database))

        resolved_map = {
            identifier: direction_to_master.get(identifier, identifier)
            for identifier in requested
            if identifier in direction_to_master
        }
        masters = set(resolved_map.values())
        crossrefs: dict[str, set[tuple[str, str]]] = {
            master: set() for master in masters
        }
        for master_id, xref_id, database in rows:
            source = self._source_map.get(database)
            if master_id in masters and source is not None:
                crossrefs[master_id].add((source, xref_id))

        now = datetime.now(timezone.utc).isoformat()
        terms: dict[tuple[str, str], ExternalTermRecord] = {}
        relationships = []
        assertions = []
        for master_id in sorted(masters):
            terms[("rhea", master_id)] = ExternalTermRecord(
                source="rhea",
                identifier=master_id,
                term_type="reaction",
                source_version=self.resource_version,
            )
            for source, identifier in sorted(crossrefs[master_id]):
                terms[(source, identifier)] = ExternalTermRecord(
                    source=source,
                    identifier=identifier,
                    term_type="reaction",
                    source_version=self.resource_version,
                )
                relationships.append(
                    ExternalTermRelationshipRecord(
                        subject_source="rhea",
                        subject_identifier=master_id,
                        predicate="cross_references",
                        object_source=source,
                        object_identifier=identifier,
                        evidence=(
                            ProviderRelationshipEvidenceRecord(
                                provider=self.name,
                                retrieval_method="rhea2xrefs_tsv",
                                run_id=run_id,
                                source_identifier=master_id,
                                resource_version=self.resource_version,
                                retrieved_at=now,
                            ),
                        ),
                    )
                )

        for annotation in relevant:
            identifier = self._normalize_identifier(annotation.identifier)
            master_id = resolved_map.get(identifier)
            if master_id is None:
                continue
            assertions.append(
                EnrichmentAssertionRecord(
                    entity_id=annotation.entity_id,
                    predicate="maps_to_rhea_reaction",
                    term_source="rhea",
                    term_identifier=master_id,
                    evidence=(
                        EntityAssertionEvidenceRecord(
                            provider=self.name,
                            evidence_type="source_model_annotation",
                            retrieval_method="rhea2xrefs_tsv",
                            run_id=run_id,
                            source_annotation_id=annotation.annotation_id,
                            source_identifier=identifier,
                            resource_version=self.resource_version,
                            retrieved_at=now,
                        ),
                    ),
                )
            )

        unresolved = sorted(requested - set(resolved_map))
        return EnrichmentResult(
            provider=self.name,
            resource_version=self.resource_version,
            terms=tuple(terms[key] for key in sorted(terms)),
            relationships=tuple(relationships),
            assertions=tuple(assertions),
            requested_identifiers=tuple(sorted(requested)),
            resolved_identifiers=tuple(sorted(resolved_map)),
            unresolved_identifiers=tuple(unresolved),
        )

    @staticmethod
    def _normalize_identifier(identifier: str) -> str:
        return identifier.strip().upper().removeprefix("RHEA:")
