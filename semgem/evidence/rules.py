from dataclasses import dataclass, field
from typing import Any

@dataclass
class EvidenceRule:
    evidence_type: str
    target_field: str
    operator: str
    weight: float
    text: str
    value: Any = None
    values: list[Any] = field(default_factory=list)


@dataclass
class ConceptDefinition:
    name: str
    entity_type: str
    description: str
    rules: list[EvidenceRule]
    minimum_score: float = 0.5


@dataclass
class EvidenceMatch:
    evidence_type: str
    target_field: str
    matched_value: str | None
    evidence_text: str
    weight: float


@dataclass
class SemanticConcept:
    concept_name: str
    entity_type: str
    entity_id: str
    confidence: float
    evidence: list[EvidenceMatch]
