import pytest

from semgem.core.records import AnnotationInputRecord
from semgem.enrichment.kegg import KeggProvider
from semgem.enrichment.metanetx import MetaNetXProvider
from semgem.enrichment.metanetx_chemistry import MetaNetXChemistryProvider
from semgem.enrichment.rhea import RheaProvider
from semgem.enrichment.sbo import SBOProvider


def test_sbo_provider_resolves_unique_terms_and_ancestor_paths(tmp_path):
    ontology_path = tmp_path / "test.obo"
    ontology_path.write_text(
        """format-version: 1.2
ontology: test

[Term]
id: SBO:0000000
name: systems biology representation

[Term]
id: SBO:0000375
name: process
is_a: SBO:0000000 ! systems biology representation

[Term]
id: SBO:0000629
name: biomass production
is_a: SBO:0000375 ! process
""",
        encoding="utf-8",
    )
    provider = SBOProvider(ontology_path)
    annotations = [
        AnnotationInputRecord(1, 10, "sbo", "SBO:0000629"),
        AnnotationInputRecord(2, 20, "sbo", "SBO_0000629"),
    ]

    result = provider.enrich(annotations, run_id=5)

    assert result.requested_identifiers == ("SBO:0000629",)
    assert result.resolved_identifiers == ("SBO:0000629",)
    assert {term.identifier for term in result.terms} == {
        "SBO:0000000",
        "SBO:0000375",
        "SBO:0000629",
    }
    assert {
        (
            relationship.subject_identifier,
            relationship.predicate,
            relationship.object_identifier,
        )
        for relationship in result.relationships
    } == {
        ("SBO:0000629", "is_a", "SBO:0000375"),
        ("SBO:0000375", "is_a", "SBO:0000000"),
    }
    assert len(result.assertions) == 2
    assert {
        assertion.evidence[0].source_annotation_id
        for assertion in result.assertions
    } == {1, 2}


def test_sbo_provider_reports_unknown_identifiers(tmp_path):
    ontology_path = tmp_path / "test.obo"
    ontology_path.write_text(
        """format-version: 1.2
ontology: test

[Term]
id: SBO:0000000
name: root
""",
        encoding="utf-8",
    )

    result = SBOProvider(ontology_path).enrich(
        [AnnotationInputRecord(1, 10, "sbo", "SBO:9999999")],
        run_id=1,
    )

    assert result.resolved_identifiers == ()
    assert result.unresolved_identifiers == ("SBO:9999999",)
    assert result.assertions == ()


def test_kegg_provider_builds_runtime_pathway_relationships_without_static_map():
    responses = {
        "/link/pathway/rn:R00771": "rn:R00771\tpath:map00010\n",
        "/get/map00010": (
            "ENTRY       map00010                    Pathway\n"
            "NAME        Glycolysis / Gluconeogenesis\n"
            "///\n"
        ),
    }

    provider = KeggProvider(request=responses.__getitem__)
    result = provider.enrich(
        [AnnotationInputRecord(1, 10, "kegg.reaction", "R00771")],
        run_id=3,
    )

    assert result.unresolved_identifiers == ()
    assert {
        (term.source, term.identifier, term.name)
        for term in result.terms
    } == {
        ("kegg.reaction", "R00771", None),
        (
            "kegg.pathway",
            "map00010",
            "Glycolysis / Gluconeogenesis",
        ),
    }
    relationship = result.relationships[0]
    assert relationship.predicate == "belongs_to_pathway"
    assert relationship.object_identifier == "map00010"
    assert result.assertions[0].entity_id == 10


def test_kegg_provider_filters_organism_specific_pathway_links():
    responses = {
        "/link/pathway/rn:R00771": (
            "rn:R00771\tpath:map00010\n"
            "rn:R00771\tpath:hsa00010\n"
        ),
        "/get/map00010": (
            "ENTRY       map00010                    Pathway\n"
            "NAME        Glycolysis / Gluconeogenesis\n"
            "///\n"
        ),
    }

    result = KeggProvider(request=responses.__getitem__).enrich(
        [AnnotationInputRecord(1, 10, "kegg.reaction", "R00771")],
        run_id=3,
    )

    assert [item.object_identifier for item in result.relationships] == [
        "map00010"
    ]


def test_kegg_provider_reuses_cached_reaction_without_network_lookup():
    class Cache:
        @staticmethod
        def external_identifiers(source):
            assert source == "kegg.reaction"
            return {"R00771"}

        @staticmethod
        def external_identifiers_with_relationship(source, predicate):
            assert source == "kegg.reaction"
            assert predicate == "belongs_to_pathway"
            return {"R00771"}

    def unexpected_request(path):
        raise AssertionError(f"Unexpected KEGG request: {path}")

    provider = KeggProvider(request=unexpected_request)
    provider.use_catalog_cache(Cache())
    result = provider.enrich(
        [AnnotationInputRecord(1, 10, "kegg.reaction", "R00771")],
        run_id=3,
    )

    assert result.resolved_identifiers == ("R00771",)
    assert result.relationships == ()
    assert result.assertions[0].evidence[0].retrieval_method == "catalog_cache"


def test_kegg_provider_normalizes_prefixed_reaction_identifier():
    requested_paths = []

    def request(path):
        requested_paths.append(path)
        return ""

    result = KeggProvider(request=request).enrich(
        [AnnotationInputRecord(1, 10, "kegg.reaction", "rn:R00771")],
        run_id=3,
    )

    assert requested_paths == ["/link/pathway/rn:R00771"]
    assert result.requested_identifiers == ("R00771",)


def test_kegg_provider_batches_catalog_reactions_created_by_other_providers():
    class Cache:
        @staticmethod
        def external_identifiers(source):
            assert source == "kegg.reaction"
            return {"R00001", "R00002"}

        @staticmethod
        def external_identifiers_with_relationship(source, predicate):
            return set()

    requested_paths = []

    def request(path):
        requested_paths.append(path)
        if path.startswith("/link/pathway/"):
            return (
                "rn:R00001\tpath:map00010\n"
                "rn:R00002\tpath:map00020\n"
            )
        return (
            "ENTRY       map00010                    Pathway\n"
            "NAME        Glycolysis / Gluconeogenesis\n"
            "///\n"
            "ENTRY       map00020                    Pathway\n"
            "NAME        Citrate cycle (TCA cycle)\n"
            "///\n"
        )

    provider = KeggProvider(request=request)
    provider.use_catalog_cache(Cache())
    result = provider.enrich([], run_id=3)

    assert requested_paths[0] == "/link/pathway/rn:R00001+rn:R00002"
    assert result.requested_identifiers == ("R00001", "R00002")
    assert {
        (item.subject_identifier, item.object_identifier)
        for item in result.relationships
    } == {
        ("R00001", "map00010"),
        ("R00002", "map00020"),
    }


def test_metanetx_provider_bridges_model_annotation_to_shared_crossrefs(tmp_path):
    xref_path = tmp_path / "reac_xref.tsv"
    xref_path.write_text(
        """### MetaNetX/MNXref reconciliation ###
#VERSION: 4.6
bigg.reaction:PGI\tMNXR1\tphosphoglucose isomerase
kegg.reaction:R00771\tMNXR1\tphosphoglucose isomerase
rhea:15905\tMNXR1\tphosphoglucose isomerase
bigg.reaction:OTHER\tMNXR2\tother
""",
        encoding="utf-8",
    )
    result = MetaNetXProvider(xref_path).enrich(
        [AnnotationInputRecord(1, 10, "bigg.reaction", "PGI")],
        run_id=4,
    )

    assert result.resource_version == "MNXref 4.6"
    assert result.requested_identifiers == ("bigg.reaction:PGI",)
    assert result.resolved_identifiers == ("bigg.reaction:PGI",)
    assert result.assertions[0].term_identifier == "MNXR1"
    assert {
        (item.object_source, item.object_identifier)
        for item in result.relationships
    } == {
        ("bigg.reaction", "PGI"),
        ("kegg.reaction", "R00771"),
        ("rhea", "15905"),
    }


def test_metanetx_chemistry_standardizes_metabolites_and_matches_reaction(
    tmp_path,
):
    chem_xref = tmp_path / "chem_xref.tsv"
    chem_xref.write_text(
        """#VERSION: 4.6
biggM:a\tMNXM10\tA
biggM:b\tMNXM20\tB
""",
        encoding="utf-8",
    )
    chem_prop = tmp_path / "chem_prop.tsv"
    chem_prop.write_text(
        """#VERSION: 4.6
MNXM10\tCompound A\tref:a\tC\t0
MNXM20\tCompound B\tref:b\tC\t0
""",
        encoding="utf-8",
    )
    reac_prop = tmp_path / "reac_prop.tsv"
    reac_prop.write_text(
        """#VERSION: 4.6
MNXR1\t1 MNXM10@MNXD1 = 1 MNXM20@MNXD1\tbiggR:RXN\t\tB
""",
        encoding="utf-8",
    )
    reac_xref = tmp_path / "reac_xref.tsv"
    reac_xref.write_text(
        """#VERSION: 4.6
bigg.reaction:RXN\tMNXR1\tA = B
kegg.reaction:R00001\tMNXR1\tA = B
""",
        encoding="utf-8",
    )

    class Database:
        @staticmethod
        def reaction_stoichiometry_rows():
            return [
                {
                    "reaction_entity_id": 30,
                    "reaction_id": "LOCAL_RXN",
                    "metabolite_entity_id": 10,
                    "compartment_free_id": "a",
                    "compartment": "c",
                    "coefficient": -1.0,
                },
                {
                    "reaction_entity_id": 30,
                    "reaction_id": "LOCAL_RXN",
                    "metabolite_entity_id": 20,
                    "compartment_free_id": "b",
                    "compartment": "c",
                    "coefficient": 1.0,
                },
            ]

    provider = MetaNetXChemistryProvider(
        chem_xref,
        reac_prop,
        reac_xref,
        chem_prop,
    )
    provider.use_catalog_cache(Database())
    result = provider.enrich(
        [
            AnnotationInputRecord(None, 10, "bigg.metabolite", "a"),
            AnnotationInputRecord(None, 20, "bigg.metabolite", "b"),
        ],
        run_id=6,
    )

    assert result.resolved_identifiers == (
        "bigg.metabolite:a",
        "bigg.metabolite:b",
    )
    assert {
        (assertion.entity_id, assertion.predicate, assertion.term_identifier)
        for assertion in result.assertions
    } == {
        (10, "maps_to_mnxref_chemical", "MNXM10"),
        (20, "maps_to_mnxref_chemical", "MNXM20"),
        (30, "matches_mnxref_reaction_signature", "MNXR1"),
    }
    assert any(
        relationship.object_source == "kegg.reaction"
        and relationship.object_identifier == "R00001"
        for relationship in result.relationships
    )


def test_metanetx_chemistry_rejects_cross_source_metabolite_disagreement(
    tmp_path,
):
    chem_xref = tmp_path / "chem_xref.tsv"
    chem_xref.write_text(
        """#VERSION: 4.6
biggM:a\tMNXM10\tA
keggC:C00001\tMNXM20\tOther A
""",
        encoding="utf-8",
    )
    reac_prop = tmp_path / "reac_prop.tsv"
    reac_prop.write_text("#VERSION: 4.6\n", encoding="utf-8")
    reac_xref = tmp_path / "reac_xref.tsv"
    reac_xref.write_text("#VERSION: 4.6\n", encoding="utf-8")

    class Database:
        @staticmethod
        def reaction_stoichiometry_rows():
            return []

    provider = MetaNetXChemistryProvider(
        chem_xref,
        reac_prop,
        reac_xref,
    )
    provider.use_catalog_cache(Database())
    result = provider.enrich(
        [
            AnnotationInputRecord(None, 10, "bigg.metabolite", "a"),
            AnnotationInputRecord(None, 10, "kegg.compound", "C00001"),
        ],
        run_id=7,
    )

    assert result.assertions == ()
    assert result.terms == ()


def test_rhea_provider_normalizes_directional_id_and_exports_kegg_bridge(tmp_path):
    xref_path = tmp_path / "rhea2xrefs.tsv"
    xref_path.write_text(
        """RHEA_ID\tDIRECTION\tMASTER_ID\tID\tDB
15904\tUN\t15904\t5.3.1.9\tEC
15905\tLR\t15904\tR00771\tKEGG_REACTION
15906\tRL\t15904\tGLUCOSE-6-P-ISOMERASE-RXN\tMETACYC
15907\tBI\t15904\tR-HSA-123\tREACTOME
20000\tUN\t20000\tR00001\tKEGG_REACTION
""",
        encoding="utf-8",
    )
    result = RheaProvider(xref_path).enrich(
        [AnnotationInputRecord(2, 20, "rhea", "RHEA:15905")],
        run_id=5,
    )

    assert result.resolved_identifiers == ("15905",)
    assert result.assertions[0].term_identifier == "15904"
    assert {
        (item.object_source, item.object_identifier)
        for item in result.relationships
    } == {
        ("kegg.reaction", "R00771"),
        ("metacyc.reaction", "GLUCOSE-6-P-ISOMERASE-RXN"),
        ("reactome.reaction", "R-HSA-123"),
    }


@pytest.mark.parametrize("requests_per_second", [0, -1])
def test_kegg_provider_rejects_nonpositive_rate_limit(requests_per_second):
    with pytest.raises(
        ValueError,
        match="requests_per_second must be greater than zero",
    ):
        KeggProvider(requests_per_second=requests_per_second)
