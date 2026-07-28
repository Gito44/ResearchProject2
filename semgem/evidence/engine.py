from collections import defaultdict
from typing import Any, Iterable

from semgem.evidence.concepts import ConceptRegistry, normalize_label
from semgem.evidence.rules import (
    CandidateEvidence,
    EvidencePolicy,
    ModelEvidenceRule,
    ScoredConcept,
    ScoredEvidence,
)


class ModelEvidenceGenerator:
    def __init__(self, policy: EvidencePolicy, registry: ConceptRegistry):
        self.policy = policy
        self.registry = registry

    def generate(self, database) -> list[CandidateEvidence]:
        candidates = []
        entities = database.evidence_entity_rows()
        for entity in entities:
            for rule in self.policy.model_rules:
                if entity["entity_type"] != rule.entity_type:
                    continue
                matched, observed = self._evaluate(rule, entity)
                if not matched:
                    continue
                definition = self.policy.definitions[rule.evidence_code]
                candidates.append(
                    CandidateEvidence(
                        entity_id=entity["entity_id"],
                        concept_id=rule.concept_id,
                        evidence_code=rule.evidence_code,
                        source=definition.source,
                        explanation=definition.description,
                        observed_value=observed,
                    )
                )
            if entity["entity_type"] != "reaction":
                continue
            for field, evidence_code in (
                ("name", "model_name_label_match"),
                ("subsystem", "model_subsystem_label_match"),
            ):
                observed = entity.get(field)
                for concept_id in self.registry.match_label(observed):
                    definition = self.policy.definitions[evidence_code]
                    candidates.append(
                        CandidateEvidence(
                            entity_id=entity["entity_id"],
                            concept_id=concept_id,
                            evidence_code=evidence_code,
                            source=definition.source,
                            explanation=definition.description,
                            observed_value=str(observed),
                        )
                    )
        return candidates

    @staticmethod
    def _evaluate(
        rule: ModelEvidenceRule,
        entity: dict[str, Any],
    ) -> tuple[bool, str | None]:
        value = entity.get(rule.target_field)

        if rule.operator == "nonzero":
            matched = value is not None and float(value) != 0.0
            return matched, str(value) if matched else None
        if rule.operator == "contains":
            if value is None:
                return False, None
            matched = str(rule.value).lower() in str(value).lower()
            return matched, str(rule.value) if matched else None
        if rule.operator == "contains_any":
            if value is None:
                return False, None
            text = str(value).lower()
            matches = [str(item) for item in rule.values if str(item).lower() in text]
            return bool(matches), ", ".join(matches) if matches else None
        if rule.operator == "contains_all_groups":
            if value is None:
                return False, None
            text = str(value).lower()
            matches = []
            for group in rule.value_groups:
                group_matches = [
                    str(item) for item in group if str(item).lower() in text
                ]
                if not group_matches:
                    return False, None
                matches.append(group_matches[0])
            return True, ", ".join(matches)
        if rule.operator == "contains_all_normalized_groups":
            if value is None:
                return False, None
            normalized_text = f" {normalize_label(str(value))} "
            matches = []
            for group in rule.value_groups:
                group_matches = []
                for item in group:
                    normalized_item = normalize_label(str(item))
                    if normalized_item and f" {normalized_item} " in normalized_text:
                        group_matches.append(str(item))
                if not group_matches:
                    return False, None
                matches.append(group_matches[0])
            return True, ", ".join(matches)
        if rule.operator == "equals":
            matched = value == rule.value
            return matched, str(value) if matched else None
        if rule.operator == "startswith":
            if value is None:
                return False, None
            matched = str(value).startswith(str(rule.value))
            return matched, str(rule.value) if matched else None
        raise ValueError(f"Unknown model-rule operator: {rule.operator}")


class ExternalEvidenceGenerator:
    def __init__(self, registry: ConceptRegistry, policy: EvidencePolicy):
        self.registry = registry
        self.policy = policy

    def generate(self, database) -> list[CandidateEvidence]:
        candidates = []
        for row in database.external_evidence_rows():
            # The v0.5 canonical vocabulary is reaction-level only.
            if row["entity_type"] != "reaction":
                continue
            concept_ids = self.registry.match_label(row["term_name"])
            for concept_id in concept_ids:
                evidence_code = self._evidence_code(row)
                if evidence_code not in self.policy.definitions:
                    continue
                definition = self.policy.definitions[evidence_code]
                candidates.append(
                    CandidateEvidence(
                        entity_id=row["entity_id"],
                        concept_id=concept_id,
                        evidence_code=evidence_code,
                        source=definition.source,
                        explanation=definition.description,
                        observed_value=row["term_name"],
                        annotation_id=row["source_annotation_id"],
                        assertion_id=row["assertion_id"],
                        relationship_id=row["relationship_id"],
                    )
                )
        return candidates

    @staticmethod
    def _evidence_code(row: dict[str, Any]) -> str:
        provider = row["provider"]
        distance = row["distance"]
        predicate = row["predicate"]
        if provider == "sbo":
            return (
                "sbo_term_label_match"
                if distance == 0
                else "sbo_ancestor_label_match"
            )
        if provider == "kegg" and predicate == "belongs_to_pathway":
            return "kegg_pathway_label_match"
        if provider == "metanetx" and predicate == "belongs_to_pathway":
            return "metanetx_bridged_pathway_label_match"
        if provider == "rhea" and predicate == "belongs_to_pathway":
            return "rhea_bridged_pathway_label_match"
        return "external_term_label_match"


class EvidenceScorer:
    def __init__(self, policy: EvidencePolicy, concepts):
        self.policy = policy
        self.concepts = concepts

    def score(self, candidates: Iterable[CandidateEvidence]) -> list[ScoredConcept]:
        grouped: dict[tuple[int, str], list[CandidateEvidence]] = defaultdict(list)
        for candidate in candidates:
            grouped[(candidate.entity_id, candidate.concept_id)].append(candidate)

        accepted = []
        for (entity_id, concept_id), matches in grouped.items():
            # One occurrence of a fixed evidence code can contribute to a
            # conclusion. Repeated annotations cannot inflate the score.
            unique = {}
            for match in matches:
                unique.setdefault(match.evidence_code, match)
            scored = tuple(
                ScoredEvidence(
                    candidate=match,
                    weight=self.policy.definitions[code].weight,
                )
                for code, match in sorted(unique.items())
            )
            confidence = min(sum(item.weight for item in scored), 1.0)
            if confidence < self.policy.threshold_for(concept_id):
                continue
            accepted.append(
                ScoredConcept(
                    entity_id=entity_id,
                    concept_id=concept_id,
                    preferred_label=self.concepts[concept_id].preferred_label,
                    confidence=confidence,
                    evidence=scored,
                )
            )
        return sorted(accepted, key=lambda item: (item.entity_id, item.concept_id))
