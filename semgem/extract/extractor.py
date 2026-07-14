from semgem.core.records import (
    GeneRecord,
    MetaboliteRecord,
    ReactionGeneRecord,
    ReactionRecord,
    StoichiometryRecord,
)


class Extractor:

    def __init__(self, model):
        self.model = model

    def extract_metabolites(self) -> list[MetaboliteRecord]:
        records = []

        for metabolite in self.model.metabolites:
            records.append(MetaboliteRecord(metabolite_id=metabolite.id,
                    name=metabolite.name,
                    compartment=metabolite.compartment,
                    formula=metabolite.formula,
                    charge=metabolite.charge,
                    annotations=dict(metabolite.annotation) if metabolite.annotation else {}))

        return records

    def extract_genes(self) -> list[GeneRecord]:
        records = []

        for gene in self.model.genes:
            records.append(
                GeneRecord(
                    gene_id=gene.id,
                    name=gene.name,
                    annotations=dict(gene.annotation) if gene.annotation else {},
                )
            )

        return records

    def extract_reactions(self) -> list[ReactionRecord]:
        records = []

        for reaction in self.model.reactions:
            records.append(
                ReactionRecord(
                    reaction_id=reaction.id,
                    name=reaction.name,
                    lower_bound=float(reaction.lower_bound),
                    upper_bound=float(reaction.upper_bound),
                    objective_coefficient=float(reaction.objective_coefficient),
                    subsystem=getattr(reaction, "subsystem", None),
                    gene_reaction_rule=reaction.gene_reaction_rule,
                    equation=reaction.reaction,
                    annotations=dict(reaction.annotation) if reaction.annotation else {},
                )
            )

        return records

    def extract_reaction_genes(self) -> list[ReactionGeneRecord]:
        records = []

        for reaction in self.model.reactions:
            for gene in reaction.genes:
                records.append(
                    ReactionGeneRecord(
                        reaction_id=reaction.id,
                        gene_id=gene.id,
                    )
                )

        return records

    def extract_stoichiometry(self) -> list[StoichiometryRecord]:
        records = []

        for reaction in self.model.reactions:
            for metabolite, coefficient in reaction.metabolites.items():
                records.append(
                    StoichiometryRecord(
                        reaction_id=reaction.id,
                        metabolite_id=metabolite.id,
                        coefficient=float(coefficient),
                    )
                )

        return records
