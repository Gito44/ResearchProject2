from abc import ABC, abstractmethod
from collections.abc import Iterable

from semgem.core.records import AnnotationInputRecord, EnrichmentResult


class EnrichmentProvider(ABC):
    name: str
    annotation_sources: frozenset[str]

    def use_catalog_cache(self, database) -> None:
        """Receive catalog cache information when a provider can reuse it."""

    @abstractmethod
    def enrich(
        self,
        annotations: Iterable[AnnotationInputRecord],
        run_id: int,
    ) -> EnrichmentResult:
        """Resolve normalized annotations into provider-independent records."""
