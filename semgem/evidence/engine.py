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

    def generate(
        self,
        database,
        include_subsystem_evidence: bool = True,
    ) -> list[CandidateEvidence]:
        candidates = []
        entities = database.evidence_entity_rows()
        for entity in entities:
            if not include_subsystem_evidence:
                entity = dict(entity)
                entity["subsystem"] = ""
                entity["combined_text"] = " ".join(
                    str(entity.get(field, "") or "")
                    for field in (
                        "original_id",
                        "name",
                        "equation",
                        "metabolite_text",
                    )
                )
            for rule in self.policy.model_rules:
                if (
                    not include_subsystem_evidence
                    and rule.target_field == "subsystem"
                ):
                    continue
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
                if field == "subsystem" and not include_subsystem_evidence:
                    continue
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
            for concept_id, anchor in self.registry.match_anchors(
                entity.get("combined_text")
            ):
                definition = self.policy.definitions[
                    "model_semantic_anchor_match"
                ]
                candidates.append(
                    CandidateEvidence(
                        entity_id=entity["entity_id"],
                        concept_id=concept_id,
                        evidence_code="model_semantic_anchor_match",
                        source=definition.source,
                        explanation=definition.description,
                        observed_value=anchor,
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
        if rule.operator == "in":
            matched = value in rule.values
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
        self.registry = ConceptRegistry(concepts)

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
        return sorted(
            self._add_inherited_concepts(accepted),
            key=lambda item: (item.entity_id, item.concept_id),
        )

    def _add_inherited_concepts(
        self,
        accepted: list[ScoredConcept],
    ) -> list[ScoredConcept]:
        """Materialize broader concepts implied by accepted narrow concepts.

        A child conclusion is sufficient for its ancestors, but an ancestor
        conclusion never invents a more specific child. Directly supported
        conclusions take precedence over inherited versions.
        """
        conclusions = {
            (item.entity_id, item.concept_id): item for item in accepted
        }
        inherited_from: dict[tuple[int, str], list[ScoredConcept]] = defaultdict(list)
        for child in accepted:
            for parent_id in self.registry.ancestors(child.concept_id):
                key = (child.entity_id, parent_id)
                if key not in conclusions:
                    inherited_from[key].append(child)

        for (entity_id, parent_id), children in inherited_from.items():
            best_confidence = max(child.confidence for child in children)
            evidence = tuple(
                ScoredEvidence(
                    candidate=CandidateEvidence(
                        entity_id=entity_id,
                        concept_id=parent_id,
                        evidence_code="concept_hierarchy_inheritance",
                        source="semantic_hierarchy",
                        explanation=(
                            "A narrower accepted concept implies this broader "
                            "concept through the canonical hierarchy."
                        ),
                        observed_value=child.concept_id,
                    ),
                    weight=child.confidence,
                )
                for child in sorted(children, key=lambda item: item.concept_id)
            )
            conclusions[(entity_id, parent_id)] = ScoredConcept(
                entity_id=entity_id,
                concept_id=parent_id,
                preferred_label=self.concepts[parent_id].preferred_label,
                confidence=best_confidence,
                evidence=evidence,
            )
        return list(conclusions.values())
