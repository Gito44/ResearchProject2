from pathlib import Path

import cobra
import pytest

from semgem.extract.extractor import Extractor


@pytest.fixture
def schema_path() -> Path:
    return Path(__file__).parents[1] / "semgem" / "database" / "schema.sql"


@pytest.fixture
def small_model() -> cobra.Model:
    model = cobra.Model("test_model", name="Test model")

    substrate = cobra.Metabolite(
        "substrate_c",
        name="Substrate",
        compartment="c",
        formula="C1H2",
        charge=0,
    )
    product = cobra.Metabolite(
        "product_c",
        name="Product",
        compartment="c",
        formula="C1H2",
        charge=0,
    )
    reaction = cobra.Reaction(
        "BIOMASS_TEST",
        name="Test biomass reaction",
        lower_bound=0.0,
        upper_bound=1000.0,
    )
    reaction.add_metabolites({substrate: -1.0, product: 1.0})
    reaction.gene_reaction_rule = "gene_a"
    reaction.annotation = {
        "sbo": "SBO:0000629",
        "kegg.reaction": "R00001",
        "rhea": ["12345", "67890"],
    }
    substrate.annotation = {"kegg.compound": "C00001"}

    model.add_reactions([reaction])
    model.objective = reaction
    model.genes.get_by_id("gene_a").name = "Gene A"
    model.genes.get_by_id("gene_a").annotation = {"ncbigene": "1"}
    return model


@pytest.fixture
def extracted(small_model):
    extractor = Extractor(small_model)
    return {
        "reactions": extractor.extract_reactions(),
        "metabolites": extractor.extract_metabolites(),
        "genes": extractor.extract_genes(),
        "stoichiometry": extractor.extract_stoichiometry(),
        "reaction_genes": extractor.extract_reaction_genes(),
    }
