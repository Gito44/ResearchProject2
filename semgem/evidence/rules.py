from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ConceptDefinition:
    concept_id: str
    category: str
    preferred_label: str
    description: str = ""
    synonyms: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceDefinition:
    code: str
    source: str
    description: str
    weight: float


@dataclass(frozen=True)
class ModelEvidenceRule:
    concept_id: str
    evidence_code: str
    entity_type: str
    target_field: str
    operator: str
    value: Any = None
    values: tuple[Any, ...] = ()
    value_groups: tuple[tuple[Any, ...], ...] = ()


@dataclass(frozen=True)
class EvidencePolicy:
    default_threshold: float
    definitions: dict[str, EvidenceDefinition]
    model_rules: tuple[ModelEvidenceRule, ...]
    concept_thresholds: dict[str, float] = field(default_factory=dict)

    def threshold_for(self, concept_id: str) -> float:
        return self.concept_thresholds.get(concept_id, self.default_threshold)


@dataclass(frozen=True)
class CandidateEvidence:
    entity_id: int
    concept_id: str
    evidence_code: str
    source: str
    explanation: str
    observed_value: str | None = None
    annotation_id: int | None = None
    assertion_id: int | None = None
    relationship_id: int | None = None


@dataclass(frozen=True)
class ScoredEvidence:
    candidate: CandidateEvidence
    weight: float


@dataclass(frozen=True)
class ScoredConcept:
    entity_id: int
    concept_id: str
    preferred_label: str
    confidence: float
    evidence: tuple[ScoredEvidence, ...]
