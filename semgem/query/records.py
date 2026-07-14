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
    confidence: float


@dataclass(frozen=True)
class EvidenceResult:
    evidence_type: str
    target_field: str
    matched_value: str | None
    text: str
    weight: float


@dataclass(frozen=True)
class ConceptExplanation:
    name: str
    confidence: float
    evidence: tuple[EvidenceResult, ...]
