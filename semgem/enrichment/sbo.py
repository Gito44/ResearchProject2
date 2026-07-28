from collections import deque
from collections.abc import Iterable
from pathlib import Path
import re

import pronto

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


class SBOProvider(EnrichmentProvider):
    name = "sbo"
    annotation_sources = frozenset({"sbo"})

    def __init__(self, ontology_path: str | Path):
        self.ontology_path = Path(ontology_path)
        self.ontology = pronto.Ontology(self.ontology_path)
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
        by_identifier: dict[str, list[AnnotationInputRecord]] = {}
        for annotation in relevant:
            identifier = self._normalize_identifier(annotation.identifier)
            by_identifier.setdefault(identifier, []).append(annotation)

        terms: dict[str, ExternalTermRecord] = {}
        relationships: dict[
            tuple[str, str, str],
            ExternalTermRelationshipRecord,
        ] = {}
        assertions = []
        resolved = []
        unresolved = []

        for identifier, occurrences in sorted(by_identifier.items()):
            try:
                term = self.ontology[identifier]
            except KeyError:
                unresolved.append(identifier)
                continue

            resolved.append(identifier)
            self._collect_ancestor_path(term, run_id, terms, relationships)
            for annotation in occurrences:
                assertions.append(
                    EnrichmentAssertionRecord(
                        entity_id=annotation.entity_id,
                        predicate="has_sbo_term",
                        term_source="sbo",
                        term_identifier=identifier,
                        evidence=(
                            EntityAssertionEvidenceRecord(
                                provider=self.name,
                                evidence_type="source_model_annotation",
                                retrieval_method="packaged_obo",
                                run_id=run_id,
                                source_annotation_id=annotation.annotation_id,
                                source_identifier=identifier,
                                resource_version=self.resource_version,
                            ),
                        ),
                    )
                )

        return EnrichmentResult(
            provider=self.name,
            resource_version=self.resource_version,
            terms=tuple(terms[key] for key in sorted(terms)),
            relationships=tuple(
                relationships[key] for key in sorted(relationships)
            ),
            assertions=tuple(assertions),
            requested_identifiers=tuple(sorted(by_identifier)),
            resolved_identifiers=tuple(resolved),
            unresolved_identifiers=tuple(unresolved),
        )

    def _collect_ancestor_path(
        self,
        start,
        run_id: int,
        terms: dict[str, ExternalTermRecord],
        relationships: dict[
            tuple[str, str, str],
            ExternalTermRelationshipRecord,
        ],
    ) -> None:
        queue = deque([start])
        visited = set()
        while queue:
            term = queue.popleft()
            if term.id in visited:
                continue
            visited.add(term.id)
            terms[term.id] = self._term_record(term)

            for parent in term.superclasses(distance=1, with_self=False):
                terms[parent.id] = self._term_record(parent)
                key = (term.id, "is_a", parent.id)
                relationships[key] = ExternalTermRelationshipRecord(
                    subject_source="sbo",
                    subject_identifier=term.id,
                    predicate="is_a",
                    object_source="sbo",
                    object_identifier=parent.id,
                    evidence=(
                        ProviderRelationshipEvidenceRecord(
                            provider=self.name,
                            retrieval_method="packaged_obo",
                            run_id=run_id,
                            source_identifier=term.id,
                            resource_version=self.resource_version,
                        ),
                    ),
                )
                queue.append(parent)

    def _term_record(self, term) -> ExternalTermRecord:
        definition = str(term.definition) if term.definition is not None else None
        return ExternalTermRecord(
            source="sbo",
            identifier=term.id,
            term_type=term.namespace or "sbo_term",
            name=term.name,
            description=definition,
            source_version=self.resource_version,
            is_obsolete=term.obsolete,
        )

    def _resource_version(self) -> str:
        text = str(self.ontology.metadata)
        match = re.search(r"owl:versionInfo', '([^']+)", text)
        return match.group(1) if match else self.ontology_path.name

    @staticmethod
    def _normalize_identifier(identifier: str) -> str:
        value = identifier.strip().upper().replace("_", ":")
        if value.startswith("SBO:"):
            suffix = value.split(":", 1)[1]
            if suffix.isdigit():
                return f"SBO:{int(suffix):07d}"
        return value
