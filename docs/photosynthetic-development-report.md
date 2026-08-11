# Photosynthetic development: iJN678

## Purpose and model

iJN678, a reconstruction of *Synechocystis* sp. PCC 6803, is the current
photosynthetic development reference. Its subsystem labels are hidden before
inference. The exact local model is pinned by SHA-256 in
`evaluation/development_models.toml`.

The benchmark denominator contains 592 reactions with supported curated
pathway labels. Runtime KEGG enrichment contributed only one resolved reaction
annotation, so the development result is primarily a test of portable static
inference.

## Development result

| iJN678 measure | Static baseline | Final development result |
|---|---:|---:|
| Exact/specific reactions recovered | 178 (30.07%) | 211 (35.64%) |
| Hierarchy-compatible reactions | 447 (75.51%) | 474 (80.07%) |
| Reactions receiving any pathway conclusion | 541/863 (62.69%) | 569/863 (65.93%) |
| Strict pathway-pair precision | 77.73% | 78.73% |

Transferable anchors were added for photosystems and cyclic electron flow,
Calvin-cycle carbon fixation, porphyrin/chlorophyll and cobalamin intermediates,
and glyoxylate/photorespiratory chemistry. No iJN678 reaction IDs were added.

Following this pass, the earlier development references remain above target:
Human-GEM 82.17%, iJO1366 81.48%, and iMM904 80.28% hierarchy-compatible
recovery. The 118-pair cross-model regression now gives 99.15% precision,
99.15% recall, and 99.15% F1. iJN678 has influenced both development and that
regression, so these values must not be presented as independent validation.
