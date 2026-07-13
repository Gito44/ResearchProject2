from pathlib import Path
import tomllib

from semgem.evidence.rules import ConceptDefinition, EvidenceRule


def load_concept_definitions(path: str | Path) -> list[ConceptDefinition]:
    path = Path(path)

    with open(path, "rb") as file:
        data = tomllib.load(file)

    definitions = []

    for concept_name, concept_data in data["concepts"].items():
        rules = []

        for rule_data in concept_data.get("rules", []):
            rules.append(
                EvidenceRule(
                    evidence_type=rule_data["evidence_type"],
                    target_field=rule_data["target_field"],
                    operator=rule_data["operator"],
                    weight=float(rule_data["weight"]),
                    text=rule_data["text"],
                    value=rule_data.get("value"),
                    values=rule_data.get("values", []),
                )
            )

        definitions.append(
            ConceptDefinition(
                name=concept_name,
                entity_type=concept_data["entity_type"],
                description=concept_data.get("description", ""),
                minimum_score=float(concept_data.get("minimum_score", 0.5)),
                rules=rules,
            )
        )

    return definitions