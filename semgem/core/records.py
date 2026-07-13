from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReactionRecord:
    reaction_id: str
    name: str
    lower_bound: float
    upper_bound: float
    objective_coefficient: float
    subsystem: str | None
    gene_reaction_rule: str
    equation: str
    annotations: dict[str, Any] = field(default_factory=dict)


@dataclass
class MetaboliteRecord:
    metabolite_id: str
    name: str
    compartment: str | None
    formula: str | None
    charge: int | None
    annotations: dict[str, Any] = field(default_factory=dict)


@dataclass
class StoichiometryRecord:
    reaction_id: str
    metabolite_id: str
    coefficient: float