from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReactionRecord:
    reaction_id: str
    name: str
    lower_bound: float
    upper_bound: float
    objective_coefficient: float
    subsystem: str | None
    gene_reaction_rule: str
    equation: str
    annotations: dict[str, Any] = field(default_factory=dict)


@dataclass
class MetaboliteRecord:
    metabolite_id: str
    name: str
    compartment: str | None
    formula: str | None
    charge: int | None
    annotations: dict[str, Any] = field(default_factory=dict)


@dataclass
class StoichiometryRecord:
    reaction_id: str
    metabolite_id: str
    coefficient: float


@dataclass
class GeneRecord:
    gene_id: str
    name: str
    annotations: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReactionGeneRecord:
    reaction_id: str
    gene_id: str


@dataclass(frozen=True)
class ExternalTermRecord:
    source: str
    identifier: str
    term_type: str
    name: str | None = None
    description: str | None = None
    source_version: str | None = None
    is_obsolete: bool = False


@dataclass(frozen=True)
class ExternalTermRelationshipRecord:
    subject_source: str
    subject_identifier: str
    predicate: str
    object_source: str
    object_identifier: str
    evidence: tuple["ProviderRelationshipEvidenceRecord", ...] = ()


@dataclass(frozen=True)
class ProviderRelationshipEvidenceRecord:
    provider: str
    retrieval_method: str
    run_id: int | None = None
    source_identifier: str | None = None
    resource_version: str | None = None
    retrieved_at: str | None = None
    details: str | None = None


@dataclass(frozen=True)
class EntityAssertionEvidenceRecord:
    provider: str
    evidence_type: str
    retrieval_method: str
    relationship_id: int | None = None
    run_id: int | None = None
    source_annotation_id: int | None = None
    source_identifier: str | None = None
    resource_version: str | None = None
    retrieved_at: str | None = None
    details: str | None = None


@dataclass(frozen=True)
class EnrichmentAssertionRecord:
    entity_id: int
    predicate: str
    term_source: str
    term_identifier: str
    evidence: tuple[EntityAssertionEvidenceRecord, ...] = ()


@dataclass(frozen=True)
class AnnotationInputRecord:
    annotation_id: int
    entity_id: int
    source: str
    identifier: str


@dataclass(frozen=True)
class EnrichmentResult:
    provider: str
    resource_version: str | None
    terms: tuple[ExternalTermRecord, ...] = ()
    relationships: tuple[ExternalTermRelationshipRecord, ...] = ()
    assertions: tuple[EnrichmentAssertionRecord, ...] = ()
    requested_identifiers: tuple[str, ...] = ()
    resolved_identifiers: tuple[str, ...] = ()
    unresolved_identifiers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
