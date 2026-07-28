from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from semgem.enrichment.base import EnrichmentProvider
from semgem.evidence.engine import (
    EvidenceScorer,
    ExternalEvidenceGenerator,
    ModelEvidenceGenerator,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ProviderRunSummary:
    provider: str
    status: str
    requested: int
    resolved: int
    unresolved: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class PipelineSummary:
    providers: tuple[ProviderRunSummary, ...]
    candidate_count: int
    concept_count: int


class SemanticPipeline:
    def __init__(self, registry, policy):
        self.registry = registry
        self.policy = policy

    def run(
        self,
        database,
        providers: Iterable[EnrichmentProvider],
    ) -> PipelineSummary:
        provider_summaries = []
        all_annotations = database.annotation_inputs()

        for provider in providers:
            relevant = [
                annotation
                for annotation in all_annotations
                if annotation.source in provider.annotation_sources
            ]
            run_id = database.start_enrichment_run(
                provider=provider.name,
                started_at=utc_now(),
                resource_version=getattr(provider, "resource_version", None),
            )
            try:
                provider.use_catalog_cache(database)
                result = provider.enrich(relevant, run_id)
                database.store_enrichment(
                    result.terms,
                    result.relationships,
                    result.assertions,
                )
                status = (
                    "partial"
                    if result.unresolved_identifiers or result.warnings
                    else "completed"
                )
                error_summary = "; ".join(result.warnings) or None
                database.finish_enrichment_run(
                    run_id=run_id,
                    status=status,
                    completed_at=utc_now(),
                    requested_count=len(result.requested_identifiers),
                    resolved_count=len(result.resolved_identifiers),
                    unresolved_count=len(result.unresolved_identifiers),
                    error_summary=error_summary,
                )
                provider_summaries.append(
                    ProviderRunSummary(
                        provider=provider.name,
                        status=status,
                        requested=len(result.requested_identifiers),
                        resolved=len(result.resolved_identifiers),
                        unresolved=len(result.unresolved_identifiers),
                        warnings=result.warnings,
                    )
                )
            except Exception as error:
                database.finish_enrichment_run(
                    run_id=run_id,
                    status="failed",
                    completed_at=utc_now(),
                    requested_count=len({item.identifier for item in relevant}),
                    resolved_count=0,
                    unresolved_count=len({item.identifier for item in relevant}),
                    error_summary=str(error),
                )
                provider_summaries.append(
                    ProviderRunSummary(
                        provider=provider.name,
                        status="failed",
                        requested=len({item.identifier for item in relevant}),
                        resolved=0,
                        unresolved=len({item.identifier for item in relevant}),
                        warnings=(str(error),),
                    )
                )

        candidates = ModelEvidenceGenerator(
            self.policy,
            self.registry,
        ).generate(database)
        candidates.extend(
            ExternalEvidenceGenerator(self.registry, self.policy).generate(database)
        )
        concepts = EvidenceScorer(
            self.policy,
            self.registry.concepts,
        ).score(candidates)
        database.replace_semantic_concepts(concepts)
        return PipelineSummary(
            providers=tuple(provider_summaries),
            candidate_count=len(candidates),
            concept_count=len(concepts),
        )
