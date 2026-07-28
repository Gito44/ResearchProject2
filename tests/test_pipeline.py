from pathlib import Path
from urllib.error import URLError

from semgem.database.sqlite import SemanticDatabase
from semgem.enrichment.kegg import KeggProvider
from semgem.evidence.concepts import ConceptRegistry
from semgem.evidence.load_rules import load_concepts, load_evidence_policy
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
