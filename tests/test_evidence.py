from pathlib import Path

import pytest

from semgem.evidence.engine import EvidenceEngine
from semgem.evidence.load_rules import load_concept_definitions
from semgem.evidence.rules import ConceptDefinition, EvidenceRule


def test_packaged_rules_load():
    rules_path = (
        Path(__file__).parents[1]
        / "semgem"
        / "resources"
        / "evidence_rules.toml"
    )
    definitions = load_concept_definitions(rules_path)
    names = {definition.name for definition in definitions}

    assert names == {
        "objective_reaction",
        "biomass_reaction",
        "exchange_reaction",
        "oxygen_exchange",
    }


@pytest.mark.parametrize(
    ("operator", "target_field", "value", "values", "expected_value"),
    [
        ("nonzero", "objective_coefficient", None, [], "1.0"),
        ("contains", "combined_text", "biomass", [], "biomass"),
        ("contains_any", "combined_text", None, ["missing", "biomass"], "biomass"),
        ("equals", "reaction_id", "BIOMASS_TEST", [], "BIOMASS_TEST"),
        ("startswith", "reaction_id", "BIO", [], "BIO"),
        ("in", "annotations.sbo", None, ["SBO:0000629"], "SBO:0000629"),
    ],
)
def test_rule_operators_record_the_matched_value(
    extracted, operator, target_field, value, values, expected_value
):
    definition = ConceptDefinition(
        name="test_concept",
        entity_type="reaction",
        description="Test concept",
        minimum_score=0.5,
        rules=[
            EvidenceRule(
                evidence_type="test",
                target_field=target_field,
                operator=operator,
                weight=0.5,
                text="Test evidence",
                value=value,
                values=values,
            )
        ],
    )

    concepts = EvidenceEngine([definition]).classify_reactions(
        extracted["reactions"]
    )

    assert len(concepts) == 1
    assert concepts[0].evidence[0].target_field == target_field
    assert concepts[0].evidence[0].matched_value == expected_value


def test_score_is_capped_at_one(extracted):
    definition = ConceptDefinition(
        name="test_concept",
        entity_type="reaction",
        description="Test concept",
        minimum_score=0.5,
        rules=[
            EvidenceRule("one", "combined_text", "contains", 0.7, "one", "biomass"),
            EvidenceRule("two", "objective_coefficient", "nonzero", 0.7, "two"),
        ],
    )

    concept = EvidenceEngine([definition]).classify_reactions(
        extracted["reactions"]
    )[0]
    assert concept.confidence == 1.0
