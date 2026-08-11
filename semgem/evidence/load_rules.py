from pathlib import Path
import tomllib

from semgem.evidence.rules import (
    ConceptDefinition,
    EvidenceDefinition,
    EvidencePolicy,
    ModelEvidenceRule,
)
from semgem.evidence.concepts import ConceptRegistry


def load_concepts(path: str | Path) -> dict[str, ConceptDefinition]:
    with Path(path).open("rb") as file:
        data = tomllib.load(file)

    declared_parents: dict[str, list[str]] = {}
    for parent_id, child_ids in data.get("hierarchy", {}).get("parents", {}).items():
        for child_id in child_ids:
            declared_parents.setdefault(child_id, []).append(parent_id)

    concepts = {}
    for concept_id, raw in data.get("concepts", {}).items():
        if ":" not in concept_id:
            raise ValueError(
                f"Canonical concept '{concept_id}' must use a category-qualified ID."
            )
        concept = ConceptDefinition(
            concept_id=concept_id,
            category=raw["category"],
            preferred_label=raw["preferred_label"],
            description=raw.get("description", ""),
            synonyms=tuple(raw.get("synonyms", [])),
            parents=tuple(
                dict.fromkeys(
                    [
                        *raw.get("parents", []),
                        *declared_parents.get(concept_id, []),
                    ]
                )
            ),
            anchors=tuple(raw.get("anchors", [])),
            anchor_fragments=tuple(raw.get("anchor_fragments", [])),
        )
        if concept.category != concept_id.split(":", 1)[0]:
            raise ValueError(
                f"Concept '{concept_id}' category does not match its identifier."
            )
        concepts[concept_id] = concept
    for concept in concepts.values():
        for parent_id in concept.parents:
            if parent_id not in concepts:
                raise ValueError(
                    f"Concept '{concept.concept_id}' has unknown parent "
                    f"'{parent_id}'."
                )
            if concepts[parent_id].category != concept.category:
                raise ValueError(
                    f"Concept '{concept.concept_id}' and parent '{parent_id}' "
                    "must use the same category."
                )
    ConceptRegistry(concepts).validate_hierarchy()
    return concepts


def load_evidence_policy(
    path: str | Path,
    concepts: dict[str, ConceptDefinition],
) -> EvidencePolicy:
    with Path(path).open("rb") as file:
        data = tomllib.load(file)

    definitions = {
        code: EvidenceDefinition(
            code=code,
            source=raw["source"],
            description=raw["description"],
            weight=float(raw["weight"]),
        )
        for code, raw in data.get("evidence", {}).items()
    }
    for definition in definitions.values():
        if not 0.0 <= definition.weight <= 1.0:
            raise ValueError(
                f"Evidence '{definition.code}' weight must be between 0 and 1."
            )

    model_rules = []
    for raw in data.get("model_rules", []):
        concept_id = raw["concept_id"]
        evidence_code = raw["evidence_code"]
        if concept_id not in concepts:
            raise ValueError(f"Unknown concept in evidence rule: {concept_id}.")
        if evidence_code not in definitions:
            raise ValueError(f"Unknown evidence code in model rule: {evidence_code}.")
        model_rules.append(
            ModelEvidenceRule(
                concept_id=concept_id,
                evidence_code=evidence_code,
                entity_type=raw["entity_type"],
                target_field=raw["target_field"],
                operator=raw["operator"],
                value=raw.get("value"),
                values=tuple(raw.get("values", [])),
                value_groups=tuple(
                    tuple(group) for group in raw.get("value_groups", [])
                ),
            )
        )

    default_threshold = float(data["scoring"]["default_threshold"])
    concept_thresholds = {
        concept_id: float(threshold)
        for concept_id, threshold in data.get("concept_thresholds", {}).items()
    }
    unknown_thresholds = set(concept_thresholds) - set(concepts)
    if unknown_thresholds:
        raise ValueError(
            "Thresholds reference unknown concepts: "
            + ", ".join(sorted(unknown_thresholds))
        )
    for concept_id, threshold in {
        "__default__": default_threshold,
        **concept_thresholds,
    }.items():
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(
                f"Threshold for '{concept_id}' must be between 0 and 1."
            )

    return EvidencePolicy(
        default_threshold=default_threshold,
        definitions=definitions,
        model_rules=tuple(model_rules),
        concept_thresholds=concept_thresholds,
    )
