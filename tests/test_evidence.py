from pathlib import Path

import pytest

from semgem.evidence.concepts import ConceptRegistry, normalize_label
from semgem.evidence.engine import (
    EvidenceScorer,
    ExternalEvidenceGenerator,
    ModelEvidenceGenerator,
)
from semgem.evidence.load_rules import load_concepts, load_evidence_policy
from semgem.evidence.rules import CandidateEvidence


def resource_path(name: str) -> Path:
    return Path(__file__).parents[1] / "semgem" / "resources" / name


def loaded_policy():
    concepts = load_concepts(resource_path("concepts.toml"))
    return concepts, load_evidence_policy(
        resource_path("evidence_rules.toml"),
        concepts,
    )


def test_packaged_concepts_and_policy_load():
    concepts, policy = loaded_policy()

    assert len(concepts) == 84
    assert "pathway:glycolysis" in concepts
    assert "reaction_type:biochemical_reaction" in concepts
    assert "pathway:nucleotide_metabolism" in concepts
    assert "pathway:cofactor_biosynthesis" in concepts
    assert "kegg_pathway_label_match" in policy.definitions
    assert policy.threshold_for("objective:model_objective") == 1.0


def test_label_normalization_and_synonym_matching():
    concepts, _ = loaded_policy()
    registry = ConceptRegistry(concepts)

    assert normalize_label(" Glycolysis / Gluconeogenesis ") == (
        "glycolysis gluconeogenesis"
    )
    assert registry.match_label("glycolysis & gluconeogenesis") == (
        "pathway:glycolysis",
    )
    assert registry.match_label("glycolysi") == ()


@pytest.mark.parametrize(
    ("encoded_label", "expected_concept"),
    [
        ("S_Fatty_Acid__Biosynthesis", "pathway:fatty_acid_metabolism"),
        ("S_GlycolysisGluconeogenesis", "pathway:glycolysis"),
        (
            "S_Purine_and_Pyrimidine_Biosynthesis",
            "pathway:purine_and_pyrimidine_biosynthesis",
        ),
    ],
)
def test_bigg_style_encoded_subsystem_labels_are_decoded(
    encoded_label,
    expected_concept,
):
    concepts, _ = loaded_policy()

    assert ConceptRegistry(concepts).match_label(encoded_label) == (
        expected_concept,
    )


def test_compact_matching_is_not_applied_to_ordinary_labels():
    concepts, _ = loaded_policy()

    assert ConceptRegistry(concepts).match_label("GlycolysisGluconeogenesis") == ()


def test_canonical_labels_and_synonyms_have_no_accidental_collisions():
    concepts, _ = loaded_policy()
    registry = ConceptRegistry(concepts)

    collisions = {
        label: concept_ids
        for label, concept_ids in registry._label_index.items()
        if len(concept_ids) > 1
    }

    assert collisions == {}


@pytest.mark.parametrize(
    ("provider_label", "expected_concept"),
    [
        ("Citrate cycle (TCA cycle)", "pathway:tricarboxylic_acid_cycle"),
        ("Biosynthesis of cofactors", "pathway:cofactor_biosynthesis"),
        ("Nucleotide metabolism", "pathway:nucleotide_metabolism"),
        ("Purine metabolism", "pathway:purine_metabolism"),
        ("Pyrimidine metabolism", "pathway:pyrimidine_metabolism"),
        ("Fatty acid metabolism", "pathway:fatty_acid_metabolism"),
        (
            "Carbon fixation by Calvin cycle",
            "pathway:carbon_fixation",
        ),
        (
            "Pentose and glucuronate interconversions",
            "pathway:pentose_and_glucuronate_interconversions",
        ),
        (
            "Degradation of aromatic compounds",
            "pathway:aromatic_compound_degradation",
        ),
        (
            "Valine, leucine and isoleucine degradation",
            "pathway:branched_chain_amino_acid_degradation",
        ),
    ],
)
def test_representative_provider_labels_match_canonical_concepts(
    provider_label,
    expected_concept,
):
    concepts, _ = loaded_policy()

    assert ConceptRegistry(concepts).match_label(provider_label) == (
        expected_concept,
    )


def test_calibrated_evidence_tiers_and_thresholds():
    _, policy = loaded_policy()

    assert policy.default_threshold == 0.75
    assert policy.definitions["model_name_label_match"].weight == 0.70
    assert policy.definitions["model_subsystem_label_match"].weight == 0.80
    assert policy.definitions["kegg_pathway_label_match"].weight == 0.90
    assert policy.definitions["sbo_term_label_match"].weight == 0.95


def test_weak_name_match_alone_does_not_create_a_conclusion():
    concepts, policy = loaded_policy()
    database = StubDatabase(
        entity_rows=[
            {
                "entity_id": 10,
                "entity_type": "reaction",
                "original_id": "R_TEST",
                "name": "Glycolysis",
                "objective_coefficient": 0.0,
                "equation": "a -> b",
                "subsystem": "",
                "combined_text": "R_TEST Glycolysis a -> b",
            }
        ]
    )

    candidates = ModelEvidenceGenerator(
        policy,
        ConceptRegistry(concepts),
    ).generate(database)
    scored = EvidenceScorer(policy, concepts).score(candidates)

    assert any(
        candidate.concept_id == "pathway:glycolysis"
        and candidate.evidence_code == "model_name_label_match"
        for candidate in candidates
    )
    assert all(
        conclusion.concept_id != "pathway:glycolysis"
        for conclusion in scored
    )


class StubDatabase:
    def __init__(self, entity_rows=None, external_rows=None):
        self._entity_rows = entity_rows or []
        self._external_rows = external_rows or []

    def evidence_entity_rows(self):
        return self._entity_rows

    def external_evidence_rows(self):
        return self._external_rows


def test_model_evidence_is_generated_before_scoring():
    _, policy = loaded_policy()
    database = StubDatabase(
        entity_rows=[
            {
                "entity_id": 10,
                "entity_type": "reaction",
                "original_id": "BIOMASS_TEST",
                "name": "Biomass reaction",
                "objective_coefficient": 1.0,
                "equation": "a -> b",
                "subsystem": "",
                "combined_text": "BIOMASS_TEST Biomass reaction a -> b",
            }
        ]
    )

    concepts, _ = loaded_policy()
    candidates = ModelEvidenceGenerator(
        policy,
        ConceptRegistry(concepts),
    ).generate(database)

    assert {candidate.evidence_code for candidate in candidates} >= {
        "objective_coefficient_nonzero",
        "biomass_text_match",
        "biomass_objective_support",
    }
    assert all(not hasattr(candidate, "weight") for candidate in candidates)


def test_model_subsystem_can_target_the_same_canonical_pathway():
    concepts, policy = loaded_policy()
    database = StubDatabase(
        entity_rows=[
            {
                "entity_id": 10,
                "entity_type": "reaction",
                "original_id": "R_TEST",
                "name": "Uninformative reaction",
                "objective_coefficient": 0.0,
                "equation": "a -> b",
                "subsystem": "Glycolysis / Gluconeogenesis",
                "combined_text": "R_TEST Uninformative reaction a -> b",
            }
        ]
    )

    candidates = ModelEvidenceGenerator(
        policy,
        ConceptRegistry(concepts),
    ).generate(database)

    assert any(
        candidate.concept_id == "pathway:glycolysis"
        and candidate.evidence_code == "model_subsystem_label_match"
        for candidate in candidates
    )


def test_oxygen_rule_does_not_treat_co2_as_o2():
    concepts, policy = loaded_policy()
    database = StubDatabase(
        entity_rows=[
            {
                "entity_id": 10,
                "entity_type": "reaction",
                "original_id": "EX_co2_e",
                "name": "CO2 exchange",
                "objective_coefficient": 0.0,
                "equation": "co2_e <=>",
                "subsystem": "",
                "combined_text": "EX_co2_e CO2 exchange co2_e <=>",
            },
            {
                "entity_id": 11,
                "entity_type": "reaction",
                "original_id": "EX_o2_e",
                "name": "O2 exchange",
                "objective_coefficient": 0.0,
                "equation": "o2_e <=>",
                "subsystem": "",
                "combined_text": "EX_o2_e O2 exchange o2_e <=>",
            },
            {
                "entity_id": 12,
                "entity_type": "reaction",
                "original_id": "EX_LPS2_ST_e",
                "name": "O:2 antigen exchange",
                "objective_coefficient": 0.0,
                "equation": "lps_e <=>",
                "subsystem": "",
                "combined_text": "EX_LPS2_ST_e O:2 antigen exchange lps_e <=>",
            },
        ]
    )

    candidates = ModelEvidenceGenerator(
        policy,
        ConceptRegistry(concepts),
    ).generate(database)
    oxygen_entities = {
        candidate.entity_id
        for candidate in candidates
        if candidate.evidence_code == "oxygen_exchange_pattern"
    }

    assert oxygen_entities == {11}


@pytest.mark.parametrize(
    ("reaction_id", "expected_concept"),
    [
        ("DM_test_c", "reaction_type:demand_reaction"),
        ("SK_test_c", "reaction_type:sink_reaction"),
        ("ATPM", "objective:atp_maintenance"),
        ("EX_co2_e", "exchange:carbon_dioxide"),
        ("EX_glc__D_e", "exchange:glucose"),
        ("EX_ac_e", "exchange:acetate"),
        ("EX_nh4_e", "exchange:ammonium"),
        ("EX_no3_e", "exchange:nitrate"),
        ("EX_pi_e", "exchange:phosphate"),
        ("EX_so4_e", "exchange:sulfate"),
        ("EX_photon_e", "exchange:photon"),
    ],
)
def test_conservative_id_rules_assign_specific_concepts(
    reaction_id,
    expected_concept,
):
    concepts, policy = loaded_policy()
    database = StubDatabase(
        entity_rows=[
            {
                "entity_id": 10,
                "entity_type": "reaction",
                "original_id": reaction_id,
                "name": "",
                "objective_coefficient": 0.0,
                "equation": "",
                "subsystem": "",
                "combined_text": reaction_id,
            }
        ]
    )

    candidates = ModelEvidenceGenerator(
        policy,
        ConceptRegistry(concepts),
    ).generate(database)
    scored = EvidenceScorer(policy, concepts).score(candidates)

    assert expected_concept in {concept.concept_id for concept in scored}


@pytest.mark.parametrize(
    ("label", "expected_concept"),
    [
        ("Translocation reaction", "reaction_type:translocation_reaction"),
        ("Demand reaction", "reaction_type:demand_reaction"),
        ("Sink reaction", "reaction_type:sink_reaction"),
        ("ATP maintenance", "objective:atp_maintenance"),
        ("Oxidative Phosphorylation", "pathway:oxidative_phosphorylation"),
        (
            "Glyoxylate and dicarboxylate metabolism",
            "pathway:glyoxylate_metabolism",
        ),
        (
            "Valine, leucine, and isoleucine metabolism",
            "pathway:branched_chain_amino_acid_metabolism",
        ),
        (
            "Citrate cycle (TCA cycle)",
            "pathway:tricarboxylic_acid_cycle",
        ),
        (
            "Other carbon fixation pathways",
            "pathway:carbon_fixation",
        ),
    ],
)
def test_expanded_external_labels_match_canonical_concepts(
    label,
    expected_concept,
):
    concepts, _ = loaded_policy()

    assert expected_concept in ConceptRegistry(concepts).match_label(label)


@pytest.mark.parametrize(
    ("label", "expected_concept"),
    [
        ("Translocation reaction", "reaction_type:translocation_reaction"),
        ("Demand reaction", "reaction_type:demand_reaction"),
        ("Sink reaction", "reaction_type:sink_reaction"),
        ("ATP maintenance", "objective:atp_maintenance"),
    ],
)
def test_direct_sbo_labels_produce_accepted_concepts(label, expected_concept):
    concepts, policy = loaded_policy()
    database = StubDatabase(
        external_rows=[
            {
                "entity_id": 10,
                "entity_type": "reaction",
                "assertion_id": 2,
                "relationship_id": None,
                "distance": 0,
                "predicate": "has_sbo_term",
                "term_name": label,
                "provider": "sbo",
                "source_annotation_id": 4,
            }
        ]
    )

    candidates = ExternalEvidenceGenerator(
        ConceptRegistry(concepts),
        policy,
    ).generate(database)
    scored = EvidenceScorer(policy, concepts).score(candidates)

    assert {concept.concept_id for concept in scored} == {expected_concept}


def test_external_pathways_can_assign_multiple_concepts_to_one_reaction():
    concepts, policy = loaded_policy()
    labels = [
        "Citrate cycle (TCA cycle)",
        "Glyoxylate and dicarboxylate metabolism",
        "Other carbon fixation pathways",
    ]
    database = StubDatabase(
        external_rows=[
            {
                "entity_id": 10,
                "entity_type": "reaction",
                "assertion_id": 2,
                "relationship_id": index,
                "distance": 1,
                "predicate": "belongs_to_pathway",
                "term_name": label,
                "provider": "kegg",
                "source_annotation_id": 4,
            }
            for index, label in enumerate(labels, 1)
        ]
    )

    candidates = ExternalEvidenceGenerator(
        ConceptRegistry(concepts),
        policy,
    ).generate(database)
    scored = EvidenceScorer(policy, concepts).score(candidates)

    assert {concept.concept_id for concept in scored} == {
        "pathway:tricarboxylic_acid_cycle",
        "pathway:glyoxylate_metabolism",
        "pathway:carbon_fixation",
    }


@pytest.mark.parametrize(
    "reaction_id",
    [
        "DMATT",
        "DMSOR1",
        "SKMtex",
        "CO2t",
        "GLCt",
        "ACtex",
    ],
)
def test_strict_id_prefix_rules_avoid_similar_non_boundary_ids(reaction_id):
    concepts, policy = loaded_policy()
    database = StubDatabase(
        entity_rows=[
            {
                "entity_id": 10,
                "entity_type": "reaction",
                "original_id": reaction_id,
                "name": "",
                "objective_coefficient": 0.0,
                "equation": "",
                "subsystem": "",
                "combined_text": reaction_id,
            }
        ]
    )

    candidates = ModelEvidenceGenerator(
        policy,
        ConceptRegistry(concepts),
    ).generate(database)
    forbidden = {
        "reaction_type:demand_reaction",
        "reaction_type:sink_reaction",
        "exchange:carbon_dioxide",
        "exchange:glucose",
        "exchange:acetate",
    }

    assert not ({candidate.concept_id for candidate in candidates} & forbidden)


def test_external_label_evidence_targets_canonical_concept():
    concepts, policy = loaded_policy()
    database = StubDatabase(
        external_rows=[
            {
                "entity_id": 10,
                "entity_type": "reaction",
                "assertion_id": 2,
                "relationship_id": 3,
                "distance": 1,
                "predicate": "belongs_to_pathway",
                "term_name": "Glycolysis / Gluconeogenesis",
                "provider": "kegg",
                "source_annotation_id": 4,
            }
        ]
    )

    candidates = ExternalEvidenceGenerator(
        ConceptRegistry(concepts),
        policy,
    ).generate(database)

    assert candidates == [
        CandidateEvidence(
            entity_id=10,
            concept_id="pathway:glycolysis",
            evidence_code="kegg_pathway_label_match",
            source="kegg",
            explanation=policy.definitions[
                "kegg_pathway_label_match"
            ].description,
            observed_value="Glycolysis / Gluconeogenesis",
            annotation_id=4,
            assertion_id=2,
            relationship_id=3,
        )
    ]


def test_scorer_deduplicates_codes_caps_scores_and_rejects_weak_candidates():
    _, policy = loaded_policy()
    strong = CandidateEvidence(
        entity_id=10,
        concept_id="objective:biomass_production",
        evidence_code="biomass_text_match",
        source="model",
        explanation="text",
    )
    duplicate = CandidateEvidence(
        entity_id=10,
        concept_id="objective:biomass_production",
        evidence_code="biomass_text_match",
        source="model",
        explanation="duplicate",
    )
    support = CandidateEvidence(
        entity_id=10,
        concept_id="objective:biomass_production",
        evidence_code="biomass_objective_support",
        source="model",
        explanation="objective",
    )
    weak = CandidateEvidence(
        entity_id=11,
        concept_id="objective:biomass_production",
        evidence_code="biomass_text_match",
        source="model",
        explanation="text only",
    )

    concept_definitions, _ = loaded_policy()
    concepts = EvidenceScorer(
        policy,
        concept_definitions,
    ).score([strong, duplicate, support, weak])

    assert len(concepts) == 1
    assert concepts[0].entity_id == 10
    assert concepts[0].confidence == 1.0
    assert len(concepts[0].evidence) == 2
