# Yeast development: iMM904

## Purpose and model

iMM904 is the yeast development reference. Its subsystem labels are hidden
before inference and retained only as the development reference. The exact
local file is pinned by SHA-256 in `evaluation/development_models.toml`.

This model tests the annotation-poor fallback particularly well: its SBML
export contains no KEGG reaction annotations, so the KEGG provider resolves no
relationships. The final improvement therefore comes entirely from portable
model evidence and hierarchy, not source subsystem leakage or online pathway
lookups.

## Development result

The benchmark denominator contains 796 reactions with supported curated
pathway labels.

| iMM904 measure | Static baseline | Final development result |
|---|---:|---:|
| Exact/specific reactions recovered | 95 (11.93%) | 264 (33.17%) |
| Hierarchy-compatible reactions | 516 (64.82%) | 637 (80.03%) |
| Reactions receiving any pathway conclusion | 827/1,577 (52.44%) | 947/1,577 (60.05%) |
| Strict pathway-pair precision | 83.33% | 86.27% |

The main implementation improvement is a normalized phrase operator. It lets
the same curated enzyme phrase match both readable names such as `citrate
synthase` and encoded SBML names such as `R_citrate_synthase__mitochondrial`.
Transferable enzyme families were added for aromatic amino-acid, folate,
nucleotide, pyruvate, anaplerotic, amino-acid, vitamin, and central-carbon
pathways. No iMM904 reaction identifiers were added.

After the yeast additions, Human-GEM remains above target at 82.15% and
iJO1366 improves to 81.20% hierarchy-compatible recovery. The 118-pair
cross-model regression improves slightly to 99.06% precision, 88.98% recall,
and 93.75% F1. These are development checks, not independent validation.
