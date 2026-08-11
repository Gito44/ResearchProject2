from semgem.core.records import AnnotationInputRecord
from semgem.enrichment.identity import infer_identity_inputs


class StubDatabase:
    @staticmethod
    def evidence_entity_rows():
        return [
            {
                "entity_id": 1,
                "entity_type": "reaction",
                "original_id": "R00771_c",
            },
            {
                "entity_id": 2,
                "entity_type": "reaction",
                "original_id": "RHEA:15905",
            },
            {
                "entity_id": 3,
                "entity_type": "reaction",
                "original_id": "MNXR1_m",
            },
            {
                "entity_id": 4,
                "entity_type": "reaction",
                "original_id": "PGI",
            },
            {
                "entity_id": 5,
                "entity_type": "metabolite",
                "original_id": "R00001",
            },
        ]

    @staticmethod
    def metabolite_standardization_rows():
        return [
            {
                "entity_id": 6,
                "compartment_free_id": "glc__D",
            },
            {
                "entity_id": 7,
                "compartment_free_id": "C00031",
            },
            {
                "entity_id": 8,
                "compartment_free_id": "MNXM41",
            },
        ]


def test_strict_external_accessions_are_inferred_without_becoming_annotations():
    inputs = infer_identity_inputs(StubDatabase())

    assert inputs == [
        AnnotationInputRecord(None, 1, "kegg.reaction", "R00771"),
        AnnotationInputRecord(None, 2, "rhea", "15905"),
        AnnotationInputRecord(None, 3, "metanetx.reaction", "MNXR1"),
        AnnotationInputRecord(None, 4, "bigg.reaction", "PGI"),
        AnnotationInputRecord(None, 6, "bigg.metabolite", "glc__D"),
        AnnotationInputRecord(None, 7, "kegg.compound", "C00031"),
        AnnotationInputRecord(None, 8, "metanetx.chemical", "MNXM41"),
    ]


def test_inference_does_not_replace_an_existing_source_annotation():
    existing = [
        AnnotationInputRecord(9, 1, "kegg.reaction", "R00771"),
    ]

    inputs = infer_identity_inputs(StubDatabase(), existing)

    assert not any(item.entity_id == 1 for item in inputs)
