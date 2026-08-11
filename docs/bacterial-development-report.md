# Bacterial development: iJO1366

## Purpose and model

iJO1366 is the bacterial development reference for the current classifier.
Its source subsystem labels are hidden before inference and used only as the
development reference. The exact local file is pinned by SHA-256 in
`evaluation/development_models.toml`. iML1515 remains useful as an
annotation-poor transfer model, but its local SBML export has no subsystem
labels and therefore cannot supply pathway ground truth for this procedure.

## Development result

The baseline and final measurements use the same 1,463 reactions carrying a
supported curated pathway label.

| iJO1366 measure | Static baseline | KEGG baseline | Final development result |
|---|---:|---:|---:|
| Exact/specific reactions recovered | 70 (4.78%) | 311 (21.26%) | 394 (26.93%) |
| Hierarchy-compatible reactions | 910 (62.20%) | 1,139 (77.85%) | 1,180 (80.66%) |
| Reactions receiving any pathway conclusion | 1,213/2,583 (46.96%) | 1,454/2,583 (56.29%) | 1,499/2,583 (58.03%) |
| Strict pathway-pair precision | 90.91% | 63.86% | 59.70% |

The development additions are transferable ontology relationships and
chemistry labels rather than iJO1366 reaction identifiers. They connect
lipopolysaccharide and murein metabolism to cell-envelope biosynthesis,
membrane-lipid metabolism to lipid metabolism, nucleotide salvage to
nucleotide metabolism, and alternative-carbon metabolism to carbohydrate
metabolism. Respiratory-chain phrases add specific oxidative-phosphorylation
evidence; that concept reached 86.21% precision and 48.08% recall on iJO1366.

The result exceeds the provisional 80% hierarchy-compatible development
target. It is not independent validation, and strict exact recovery remains
substantially lower. The unchanged 118-pair cross-model regression still gives
99.05% precision, 88.14% recall, and 93.27% F1 after these additions.
