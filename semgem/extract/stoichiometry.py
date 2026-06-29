def extract_reaction_metabolites(model):
    rows = []

    for reaction in model.reactions:
        for metabolite, coefficient in reaction.metabolites.items():
            rows.append({
                "reaction_id": reaction.id,
                "metabolite_id": metabolite.id,
                "coefficient": float(coefficient)
            })

    return rows