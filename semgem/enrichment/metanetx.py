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


class MetaNetXProvider(EnrichmentProvider):
    """Resolve reaction annotations through an official MNXref xref table."""

    name = "metanetx"
    annotation_sources = frozenset(
        {
            "metanetx.reaction",
            "bigg.reaction",
            "kegg.reaction",
            "rhea",
        }
    )
    _exported_sources = frozenset(
        {
            "bigg.reaction",
            "kegg.reaction",
            "metacyc.reaction",
            "rhea",
        }
    )

    def __init__(self, xref_path: str | Path):
        self.xref_path = Path(xref_path)
        if not self.xref_path.is_file():
            raise FileNotFoundError(
                f"MetaNetX reaction xref file not found: {self.xref_path}"
            )
        self.resource_version = self._resource_version()

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
            self._xref_key(annotation.source, annotation.identifier)
            for annotation in relevant
        }
        requested.discard(None)

        xref_to_mnx: dict[str, str] = {}
        direct_mnx = {
            key.removeprefix("metanetx.reaction:")
            for key in requested
            if key.startswith("metanetx.reaction:")
        }
        for key, mnx_id, _ in self._rows():
            if key in requested:
                xref_to_mnx[key] = mnx_id
        for mnx_id in direct_mnx:
            xref_to_mnx[f"metanetx.reaction:{mnx_id}"] = mnx_id

        matched_mnx = set(xref_to_mnx.values())
        crossrefs: dict[str, set[tuple[str, str]]] = {
            mnx_id: set() for mnx_id in matched_mnx
        }
        for key, mnx_id, _ in self._rows():
            if mnx_id not in matched_mnx:
                continue
            source, identifier = self._split_xref(key)
            if source in self._exported_sources:
                crossrefs[mnx_id].add((source, identifier))

        now = datetime.now(timezone.utc).isoformat()
        terms: dict[tuple[str, str], ExternalTermRecord] = {}
        relationships = []
        assertions = []

        for mnx_id in sorted(matched_mnx):
            terms[("metanetx.reaction", mnx_id)] = ExternalTermRecord(
                source="metanetx.reaction",
                identifier=mnx_id,
                term_type="reaction",
                source_version=self.resource_version,
            )
            for source, identifier in sorted(crossrefs[mnx_id]):
                if source == "metanetx.reaction" and identifier == mnx_id:
                    continue
                terms[(source, identifier)] = ExternalTermRecord(
                    source=source,
                    identifier=identifier,
                    term_type="reaction",
                    source_version=self.resource_version,
                )
                relationships.append(
                    ExternalTermRelationshipRecord(
                        subject_source="metanetx.reaction",
                        subject_identifier=mnx_id,
                        predicate="cross_references",
                        object_source=source,
                        object_identifier=identifier,
                        evidence=(
                            ProviderRelationshipEvidenceRecord(
                                provider=self.name,
                                retrieval_method="mnxref_reac_xref",
                                run_id=run_id,
                                source_identifier=mnx_id,
                                resource_version=self.resource_version,
                                retrieved_at=now,
                            ),
                        ),
                    )
                )

        resolved_keys = set(xref_to_mnx)
        for annotation in relevant:
            key = self._xref_key(annotation.source, annotation.identifier)
            if key not in resolved_keys:
                continue
            mnx_id = xref_to_mnx[key]
            assertions.append(
                EnrichmentAssertionRecord(
                    entity_id=annotation.entity_id,
                    predicate="maps_to_mnxref_reaction",
                    term_source="metanetx.reaction",
                    term_identifier=mnx_id,
                    evidence=(
                        EntityAssertionEvidenceRecord(
                            provider=self.name,
                            evidence_type=(
                                "source_model_annotation"
                                if annotation.annotation_id is not None
                                else "model_identifier_pattern"
                            ),
                            retrieval_method="mnxref_reac_xref",
                            run_id=run_id,
                            source_annotation_id=annotation.annotation_id,
                            source_identifier=annotation.identifier,
                            resource_version=self.resource_version,
                            retrieved_at=now,
                        ),
                    ),
                )
            )

        unresolved = sorted(requested - resolved_keys)
        return EnrichmentResult(
            provider=self.name,
            resource_version=self.resource_version,
            terms=tuple(terms[key] for key in sorted(terms)),
            relationships=tuple(relationships),
            assertions=tuple(assertions),
            requested_identifiers=tuple(sorted(requested)),
            resolved_identifiers=tuple(sorted(resolved_keys)),
            unresolved_identifiers=tuple(unresolved),
        )

    def _rows(self):
        with self.xref_path.open(encoding="utf-8") as file:
            for line in file:
                if not line or line.startswith("#"):
                    continue
                fields = line.rstrip("\n").split("\t", 2)
                if len(fields) < 2:
                    continue
                key = self._normalize_file_xref(fields[0])
                if key is not None:
                    yield key, fields[1], fields[2] if len(fields) > 2 else ""

    def _resource_version(self) -> str:
        with self.xref_path.open(encoding="utf-8") as file:
            for line in file:
                if line.startswith("#VERSION:"):
                    return f"MNXref {line.split(':', 1)[1].strip()}"
                if not line.startswith("#"):
                    break
        return "MNXref"

    @classmethod
    def _normalize_file_xref(cls, value: str) -> str | None:
        source, separator, identifier = value.partition(":")
        if not separator:
            if value.startswith("MNXR"):
                return f"metanetx.reaction:{value}"
            return None
        aliases = {
            "biggR": "bigg.reaction",
            "bigg.reaction": "bigg.reaction",
            "keggR": "kegg.reaction",
            "kegg.reaction": "kegg.reaction",
            "metacycR": "metacyc.reaction",
            "metacyc.reaction": "metacyc.reaction",
            "rhea": "rhea",
            "rh": "rhea",
        }
        normalized_source = aliases.get(source)
        if normalized_source is None:
            return None
        return f"{normalized_source}:{cls._normalize_identifier(normalized_source, identifier)}"

    @classmethod
    def _xref_key(cls, source: str, identifier: str) -> str | None:
        if source not in cls.annotation_sources:
            return None
        return f"{source}:{cls._normalize_identifier(source, identifier)}"

    @staticmethod
    def _normalize_identifier(source: str, identifier: str) -> str:
        value = identifier.strip()
        if source == "kegg.reaction":
            return value.removeprefix("rn:").upper()
        if source == "rhea":
            return value.upper().removeprefix("RHEA:")
        if source == "metanetx.reaction":
            return value.upper().removeprefix("MNX:")
        return value

    @staticmethod
    def _split_xref(key: str) -> tuple[str, str]:
        return tuple(key.split(":", 1))
