from pathlib import Path
from urllib.error import URLError

from semgem.database.sqlite import SemanticDatabase
from semgem.enrichment.kegg import KeggProvider
from semgem.enrichment.metanetx import MetaNetXProvider
from semgem.enrichment.rhea import RheaProvider
from semgem.evidence.concepts import ConceptRegistry
from semgem.evidence.load_rules import load_concepts, load_evidence_policy
from semgem.extract.extractor import Extractor
from semgem.pipeline import SemanticPipeline


def test_pipeline_turns_runtime_kegg_relationship_into_stored_conclusion(
    tmp_path,
    schema_path,
    small_model,
    extracted,
):
    resources = Path(__file__).parents[1] / "semgem" / "resources"
    concepts = load_concepts(resources / "concepts.toml")
    policy = load_evidence_policy(resources / "evidence_rules.toml", concepts)
    responses = {
        "/link/pathway/rn:R00001": "rn:R00001\tpath:map00010\n",
        "/get/map00010": (
            "ENTRY       map00010                    Pathway\n"
            "NAME        Glycolysis / Gluconeogenesis\n"
            "///\n"
        ),
    }

    with SemanticDatabase(tmp_path / "catalog.sqlite", schema_path) as database:
        database.initialise()
        database.import_model(
            model=small_model,
            source_file="test.xml",
            content_hash="test-hash",
            reactions=extracted["reactions"],
            metabolites=extracted["metabolites"],
            genes=extracted["genes"],
            stoichiometry=extracted["stoichiometry"],
            reaction_genes=extracted["reaction_genes"],
        )
        summary = SemanticPipeline(
            ConceptRegistry(concepts),
            policy,
        ).run(
            database,
            [KeggProvider(request=responses.__getitem__)],
        )
        conclusion = database.conn.execute(
            """
            SELECT sc.concept_name, sc.preferred_label, sc.confidence,
                   ce.evidence_code, ce.relationship_id
            FROM semantic_concepts AS sc
            JOIN concept_evidence AS ce ON ce.concept_id = sc.id
            WHERE sc.concept_name = 'pathway:glycolysis'
            """
        ).fetchone()

    assert summary.providers[0].status == "completed"
    assert conclusion[:4] == (
        "pathway:glycolysis",
        "Glycolysis",
        0.9,
        "kegg_pathway_label_match",
    )
    assert conclusion[4] is not None


def test_pipeline_reports_partial_when_kegg_pathway_labels_fail(
    tmp_path,
    schema_path,
    small_model,
    extracted,
):
    resources = Path(__file__).parents[1] / "semgem" / "resources"
    concepts = load_concepts(resources / "concepts.toml")
    policy = load_evidence_policy(resources / "evidence_rules.toml", concepts)

    def request(path):
        if path == "/link/pathway/rn:R00001":
            return "rn:R00001\tpath:map00010\n"
        raise URLError("pathway labels unavailable")

    with SemanticDatabase(tmp_path / "catalog.sqlite", schema_path) as database:
        database.initialise()
        database.import_model(
            model=small_model,
            source_file="test.xml",
            content_hash="test-hash",
            reactions=extracted["reactions"],
            metabolites=extracted["metabolites"],
            genes=extracted["genes"],
            stoichiometry=extracted["stoichiometry"],
            reaction_genes=extracted["reaction_genes"],
        )
        summary = SemanticPipeline(
            ConceptRegistry(concepts),
            policy,
        ).run(
            database,
            [KeggProvider(request=request)],
        )

    assert summary.providers[0].status == "partial"
    assert summary.providers[0].resolved == 1
    assert summary.providers[0].unresolved == 0
    assert "pathway labels unavailable" in summary.providers[0].warnings[0]


def test_pipeline_uses_metanetx_bridge_as_input_to_batched_kegg_provider(
    tmp_path,
    schema_path,
    small_model,
):
    resources = Path(__file__).parents[1] / "semgem" / "resources"
    concepts = load_concepts(resources / "concepts.toml")
    policy = load_evidence_policy(resources / "evidence_rules.toml", concepts)
    reaction = small_model.reactions.get_by_id("BIOMASS_TEST")
    reaction.annotation = {"bigg.reaction": "PGI"}
    extractor = Extractor(small_model)
    xref_path = tmp_path / "reac_xref.tsv"
    xref_path.write_text(
        """#VERSION: 4.6
bigg.reaction:PGI\tMNXR1\tphosphoglucose isomerase
kegg.reaction:R00771\tMNXR1\tphosphoglucose isomerase
""",
        encoding="utf-8",
    )
    responses = {
        "/link/pathway/rn:R00771": "rn:R00771\tpath:map00010\n",
        "/get/map00010": (
            "ENTRY       map00010                    Pathway\n"
            "NAME        Glycolysis / Gluconeogenesis\n"
            "///\n"
        ),
    }

    with SemanticDatabase(tmp_path / "catalog.sqlite", schema_path) as database:
        database.initialise()
        database.import_model(
            model=small_model,
            source_file="test.xml",
            content_hash="test-hash",
            reactions=extractor.extract_reactions(),
            metabolites=extractor.extract_metabolites(),
            genes=extractor.extract_genes(),
            stoichiometry=extractor.extract_stoichiometry(),
            reaction_genes=extractor.extract_reaction_genes(),
        )
        summary = SemanticPipeline(
            ConceptRegistry(concepts),
            policy,
        ).run(
            database,
            [
                MetaNetXProvider(xref_path),
                KeggProvider(request=responses.__getitem__),
            ],
        )
        conclusion = database.conn.execute(
            """
            SELECT sc.concept_name, ce.evidence_code, ce.source
            FROM semantic_concepts AS sc
            JOIN concept_evidence AS ce ON ce.concept_id = sc.id
            WHERE sc.concept_name = 'pathway:glycolysis'
            """
        ).fetchone()

    assert [provider.provider for provider in summary.providers] == [
        "metanetx",
        "kegg",
    ]
    assert conclusion == (
        "pathway:glycolysis",
        "metanetx_bridged_pathway_label_match",
        "metanetx",
    )


def test_pipeline_uses_rhea_annotation_without_direct_kegg_annotation(
    tmp_path,
    schema_path,
    small_model,
):
    resources = Path(__file__).parents[1] / "semgem" / "resources"
    concepts = load_concepts(resources / "concepts.toml")
    policy = load_evidence_policy(resources / "evidence_rules.toml", concepts)
    reaction = small_model.reactions.get_by_id("BIOMASS_TEST")
    reaction.annotation = {"rhea": "15905"}
    extractor = Extractor(small_model)
    xref_path = tmp_path / "rhea2xrefs.tsv"
    xref_path.write_text(
        """RHEA_ID\tDIRECTION\tMASTER_ID\tID\tDB
15904\tUN\t15904\t5.3.1.9\tEC
15905\tLR\t15904\tR00771\tKEGG_REACTION
""",
        encoding="utf-8",
    )
    responses = {
        "/link/pathway/rn:R00771": "rn:R00771\tpath:map00010\n",
        "/get/map00010": (
            "ENTRY       map00010                    Pathway\n"
            "NAME        Glycolysis / Gluconeogenesis\n"
            "///\n"
        ),
    }

    with SemanticDatabase(tmp_path / "catalog.sqlite", schema_path) as database:
        database.initialise()
        database.import_model(
            model=small_model,
            source_file="test.xml",
            content_hash="test-hash",
            reactions=extractor.extract_reactions(),
            metabolites=extractor.extract_metabolites(),
            genes=extractor.extract_genes(),
            stoichiometry=extractor.extract_stoichiometry(),
            reaction_genes=extractor.extract_reaction_genes(),
        )
        SemanticPipeline(
            ConceptRegistry(concepts),
            policy,
        ).run(
            database,
            [
                RheaProvider(xref_path),
                KeggProvider(request=responses.__getitem__),
            ],
        )
        conclusion = database.conn.execute(
            """
            SELECT sc.concept_name, ce.evidence_code, ce.source
            FROM semantic_concepts AS sc
            JOIN concept_evidence AS ce ON ce.concept_id = sc.id
            WHERE sc.concept_name = 'pathway:glycolysis'
            """
        ).fetchone()

    assert conclusion == (
        "pathway:glycolysis",
        "rhea_bridged_pathway_label_match",
        "rhea",
    )
