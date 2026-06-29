def extract_reactions(model):
    rows = []

    for reaction in model.reactions:
        rows.append({
            "reaction_id": reaction.id,
            "name": reaction.name,
            "lower_bound": reaction.lower_bound,
            "upper_bound": reaction.upper_bound,
            "objective_coefficient": reaction.objective_coefficient,
            "subsystem": getattr(reaction, "subsystem", None),
            "gene_reaction_rule": getattr(reaction, "gene_reaction_rule", None),
            "equation": reaction.reaction,
            "annotations": dict(reaction.annotation) if reaction.annotation else {}

        })

    return rows