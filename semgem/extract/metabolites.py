def extract_metabolites(model):
    rows = []

    for metabolite in model.metabolites:
        rows.append({
            "metabolite_id": metabolite.id,
            "name": metabolite.name,
            "compartment": metabolite.compartment,
            "formula": metabolite.formula,
            "charge": metabolite.charge,
            "annotations": dict(metabolite.annotation) if metabolite.annotation else {}
        })

    return rows