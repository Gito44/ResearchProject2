from typing import Any

from semgem.evidence.rules import (
    ConceptDefinition,
    EvidenceMatch,
    EvidenceRule,
    SemanticConcept,
)


class EvidenceEngine:
    def __init__(self, concept_definitions: list[ConceptDefinition]):
        self.concept_definitions = concept_definitions

    def classify_reactions(self, reactions) -> list[SemanticConcept]:
        concepts = []

        for reaction in reactions:
            for concept_definition in self.concept_definitions:
                if concept_definition.entity_type != "reaction":
                    continue

                matched_evidence = []

                for rule in concept_definition.rules:
                    matched, matched_value = self._evaluate_rule(rule, reaction)
                    if matched:
                        matched_evidence.append(
                            EvidenceMatch(
                                evidence_type=rule.evidence_type,
                                target_field=rule.target_field,
                                matched_value=matched_value,
                                evidence_text=rule.text,
                                weight=rule.weight,
                            )
                        )

                score: float = sum(float(evidence.weight) for evidence in matched_evidence)
                confidence = min(score, 1.0)

                if confidence >= concept_definition.minimum_score:
                    concepts.append(
                        SemanticConcept(
                            concept_name=concept_definition.name,
                            entity_type=concept_definition.entity_type,
                            entity_id=reaction.reaction_id,
                            confidence=confidence,
                            evidence=matched_evidence,
                        )
                    )

        return concepts

    def _evaluate_rule(self, rule: EvidenceRule, entity) -> tuple[bool, str | None]:
        value = self._get_field_value(entity, rule.target_field)

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
            matches = [str(v) for v in rule.values if str(v).lower() in text]
            return bool(matches), ", ".join(matches) if matches else None

        if rule.operator == "equals":
            matched = value == rule.value
            return matched, str(value) if matched else None

        if rule.operator == "startswith":
            if value is None:
                return False, None
            matched = str(value).startswith(str(rule.value))
            return matched, str(rule.value) if matched else None

        if rule.operator == "in":
            if value is None:
                return False, None

            if isinstance(value, list):
                matches = [str(v) for v in value if v in rule.values]
                return bool(matches), ", ".join(matches) if matches else None

            matched = value in rule.values
            return matched, str(value) if matched else None

        raise ValueError(f"Unknown rule operator: {rule.operator}")

    def _get_field_value(self, entity, field: str) -> Any:
        if field == "combined_text":
            values = [
                getattr(entity, "reaction_id", ""),
                getattr(entity, "name", ""),
                getattr(entity, "equation", ""),
            ]
            return " ".join(str(value or "") for value in values)

        if field.startswith("annotations."):
            annotation_key = field.replace("annotations.", "")
            annotations = getattr(entity, "annotations", {}) or {}
            return annotations.get(annotation_key)

        return getattr(entity, field, None)
