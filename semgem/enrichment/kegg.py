from collections.abc import Callable, Iterable
from datetime import datetime, timezone
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

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


class KeggProvider(EnrichmentProvider):
    """Optional runtime KEGG REST provider.

    SemGEM contains no packaged KEGG mappings. All relationships are obtained
    from KEGG during the user's run and stored only in the user's catalog.
    """

    name = "kegg"
    annotation_sources = frozenset({"kegg.reaction"})
    base_url = "https://rest.kegg.jp"
    resource_version = "KEGG REST"

    def __init__(
        self,
        request: Callable[[str], str] | None = None,
        requests_per_second: float = 3.0,
    ):
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be greater than zero.")
        self._request_override = request
        self._minimum_interval = 1.0 / requests_per_second
        self._last_request = 0.0
        self._catalog_reactions: set[str] = set()
        self._cached_pathway_reactions: set[str] = set()

    def use_catalog_cache(self, database) -> None:
        self._catalog_reactions = database.external_identifiers("kegg.reaction")
        self._cached_pathway_reactions = (
            database.external_identifiers_with_relationship(
                "kegg.reaction",
                "belongs_to_pathway",
            )
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
        by_identifier: dict[str, list[AnnotationInputRecord]] = {}
        for annotation in relevant:
            identifier = self._normalize_reaction_identifier(
                annotation.identifier
            )
            by_identifier.setdefault(identifier, []).append(annotation)

        requested_ids = set(by_identifier) | self._catalog_reactions
        reaction_pathways: dict[str, set[str]] = {}
        resolved = []
        unresolved = []
        warnings = []

        cached = requested_ids & self._cached_pathway_reactions
        for identifier in sorted(cached):
            resolved.append(identifier)
            reaction_pathways[identifier] = set()

        uncached = sorted(requested_ids - cached)
        for batch in self._batches(uncached, 10):
            try:
                query = "+".join(f"rn:{identifier}" for identifier in batch)
                response = self._request(f"/link/pathway/{query}")
            except (HTTPError, URLError, TimeoutError, OSError) as error:
                unresolved.extend(batch)
                warnings.append(f"{', '.join(batch)}: {error}")
                continue
            parsed = self._parse_link_response(response)
            for identifier in batch:
                resolved.append(identifier)
                reaction_pathways[identifier] = parsed.get(identifier, set())

        pathway_ids = sorted(
            {
                pathway
                for pathways in reaction_pathways.values()
                for pathway in pathways
            }
        )
        pathway_names = {}
        for batch in self._batches(pathway_ids, 10):
            try:
                response = self._request("/get/" + "+".join(batch))
                pathway_names.update(self._parse_pathway_names(response))
            except (HTTPError, URLError, TimeoutError, OSError) as error:
                warnings.append(f"Pathway labels {', '.join(batch)}: {error}")

        now = datetime.now(timezone.utc).isoformat()
        terms: dict[tuple[str, str], ExternalTermRecord] = {}
        relationships = []
        assertions = []

        for reaction_id in sorted(requested_ids):
            if reaction_id not in resolved:
                continue
            occurrences = by_identifier.get(reaction_id, ())
            terms[("kegg.reaction", reaction_id)] = ExternalTermRecord(
                source="kegg.reaction",
                identifier=reaction_id,
                term_type="reaction",
                source_version="KEGG REST",
            )
            for annotation in occurrences:
                assertions.append(
                    EnrichmentAssertionRecord(
                        entity_id=annotation.entity_id,
                        predicate="has_kegg_reaction",
                        term_source="kegg.reaction",
                        term_identifier=reaction_id,
                        evidence=(
                            EntityAssertionEvidenceRecord(
                                provider=self.name,
                                evidence_type="source_model_annotation",
                                retrieval_method=(
                                    "catalog_cache"
                                    if reaction_id in cached
                                    else "kegg_rest"
                                ),
                                run_id=run_id,
                                source_annotation_id=annotation.annotation_id,
                                source_identifier=reaction_id,
                                resource_version="KEGG REST",
                                retrieved_at=now,
                            ),
                        ),
                    )
                )
            for pathway_id in sorted(reaction_pathways[reaction_id]):
                terms[("kegg.pathway", pathway_id)] = ExternalTermRecord(
                    source="kegg.pathway",
                    identifier=pathway_id,
                    term_type="pathway",
                    name=pathway_names.get(pathway_id),
                    source_version="KEGG REST",
                )
                relationships.append(
                    ExternalTermRelationshipRecord(
                        subject_source="kegg.reaction",
                        subject_identifier=reaction_id,
                        predicate="belongs_to_pathway",
                        object_source="kegg.pathway",
                        object_identifier=pathway_id,
                        evidence=(
                            ProviderRelationshipEvidenceRecord(
                                provider=self.name,
                                retrieval_method="kegg_rest",
                                run_id=run_id,
                                source_identifier=reaction_id,
                                resource_version="KEGG REST",
                                retrieved_at=now,
                            ),
                        ),
                    )
                )

        return EnrichmentResult(
            provider=self.name,
            resource_version="KEGG REST",
            terms=tuple(terms[key] for key in sorted(terms)),
            relationships=tuple(relationships),
            assertions=tuple(assertions),
            requested_identifiers=tuple(sorted(requested_ids)),
            resolved_identifiers=tuple(resolved),
            unresolved_identifiers=tuple(unresolved),
            warnings=tuple(warnings),
        )

    def _request(self, path: str) -> str:
        if self._request_override is not None:
            return self._request_override(path)
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._minimum_interval:
            time.sleep(self._minimum_interval - elapsed)
        with urlopen(self.base_url + path, timeout=30) as response:
            body = response.read().decode("utf-8")
        self._last_request = time.monotonic()
        return body

    @staticmethod
    def _parse_link_response(text: str) -> dict[str, set[str]]:
        pathways: dict[str, set[str]] = {}
        for line in text.splitlines():
            parts = line.split("\t")
            if len(parts) != 2:
                continue
            reaction = parts[0].removeprefix("rn:")
            pathway = parts[1].removeprefix("path:")
            if pathway.startswith("map"):
                pathways.setdefault(reaction, set()).add(pathway)
        return pathways

    @staticmethod
    def _parse_pathway_names(text: str) -> dict[str, str]:
        names = {}
        current_id = None
        for line in text.splitlines():
            if line.startswith("ENTRY"):
                fields = line.split()
                current_id = fields[1] if len(fields) > 1 else None
            elif line.startswith("NAME") and current_id:
                names[current_id] = line[12:].strip()
            elif line.startswith("///"):
                current_id = None
        return names

    @staticmethod
    def _batches(values: list[str], size: int):
        for index in range(0, len(values), size):
            yield values[index : index + size]

    @staticmethod
    def _normalize_reaction_identifier(identifier: str) -> str:
        value = identifier.strip().upper()
        if value.startswith("RN:"):
            return value.removeprefix("RN:")
        return value
