import pytest

from semgem.core.records import AnnotationInputRecord
from semgem.enrichment.kegg import KeggProvider
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


@pytest.mark.parametrize("requests_per_second", [0, -1])
def test_kegg_provider_rejects_nonpositive_rate_limit(requests_per_second):
    with pytest.raises(
        ValueError,
        match="requests_per_second must be greater than zero",
    ):
        KeggProvider(requests_per_second=requests_per_second)
