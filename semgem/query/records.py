from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSummary:
    internal_id: int
    original_id: str
    name: str | None
    source_file: str
    content_hash: str


@dataclass(frozen=True)
class EntitySummary:
    internal_id: int
    model_id: str
    entity_type: str
    original_id: str
    name: str | None


@dataclass(frozen=True)
class AnnotationResult:
    source: str
    identifier: str


@dataclass(frozen=True)
class ConceptSummary:
    name: str
    preferred_label: str
    confidence: float


@dataclass(frozen=True)
class EvidenceResult:
    evidence_code: str
    source: str
    observed_value: str | None
    explanation: str
    weight: float
    annotation_id: int | None
    assertion_id: int | None
    relationship_id: int | None


@dataclass(frozen=True)
class ConceptExplanation:
    name: str
    preferred_label: str
    confidence: float
    evidence: tuple[EvidenceResult, ...]


@dataclass(frozen=True)
class SearchMatch:
    field: str
    value: str
    source: str | None = None


@dataclass(frozen=True)
class SearchResult:
    entity: EntitySummary
    matches: tuple[SearchMatch, ...]


@dataclass(frozen=True)
class CatalogStatistics:
    model_count: int
    reaction_count: int
    metabolite_count: int
    gene_count: int
    semantic_assignment_count: int


@dataclass(frozen=True)
class CoverageSummary:
    model_id: str | None
    total_reactions: int
    pathway_reactions: int
    actionable_non_pathway_reactions: int
    actionable_reactions: int
    generic_only_reactions: int
    unclassified_reactions: int


@dataclass(frozen=True)
class ConceptAssignment:
    entity: EntitySummary
    concept: ConceptSummary


@dataclass(frozen=True)
class ProviderRunResult:
    provider: str
    status: str
    resource_version: str | None
    requested: int
    resolved: int
    unresolved: int
    started_at: str
    completed_at: str | None
    error_summary: str | None
