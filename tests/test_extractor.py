def test_extractor_creates_all_current_record_types(extracted):
    assert len(extracted["reactions"]) == 1
    assert len(extracted["metabolites"]) == 2
    assert len(extracted["genes"]) == 1
    assert len(extracted["stoichiometry"]) == 2
    assert len(extracted["reaction_genes"]) == 1

    reaction = extracted["reactions"][0]
    assert reaction.reaction_id == "BIOMASS_TEST"
    assert reaction.objective_coefficient == 1.0
    assert reaction.annotations["sbo"] == "SBO:0000629"


def test_stoichiometric_coefficients_are_preserved(extracted):
    coefficients = {
        row.metabolite_id: row.coefficient for row in extracted["stoichiometry"]
    }
    assert coefficients == {"substrate_c": -1.0, "product_c": 1.0}


def test_reaction_gene_relationship_is_extracted(extracted):
    relationship = extracted["reaction_genes"][0]
    assert relationship.reaction_id == "BIOMASS_TEST"
    assert relationship.gene_id == "gene_a"
