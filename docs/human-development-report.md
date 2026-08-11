# Human pathway-classification development

## Reference model

- Model: Human-GEM 2.0.0
- Repository commit: `635f533152dc5f7290ce04d12700eaa882273c3e`
- Source: <https://github.com/SysBioChalmers/Human-GEM>
- Reactions: 12,931
- Metabolites: 8,461
- Genes: 2,848
- Curated subsystem labels: 147
- Reactions with a subsystem label: 12,931 (100%)
- Reactions with at least one annotation: 12,931 (100%)
- Metabolites with at least one annotation: 8,461 (100%)

Human-GEM is a development model. Its subsystem labels have been inspected and
used to extend SemGEM's vocabulary; it therefore cannot be described as an
independent held-out benchmark.

## MEMOTE characterization

MEMOTE 0.17.0 was run in an isolated environment. The targeted annotation/SBO
report produced these relevant section scores:

| MEMOTE section | Score |
|---|---:|
| Metabolite annotation | 70.5% |
| Reaction annotation | 71.9% |
| Gene annotation | 46.7% |
| SBO annotation | 81.8% |

Every entity has at least one annotation, but MEMOTE expects cross-references
to many individual namespaces, so individual completeness tests still fail.
The targeted report's total score is not used because skipped consistency tests
are represented as zero. A full consistency run was substantially slower on
this 12,931-reaction model and was stopped; model selection currently uses the
relevant annotation sections plus direct inspection of the curated reference.

## Evaluation protocol

1. Read and preserve each reaction's curated subsystem as the reference.
2. Clear subsystem fields before extraction so they cannot become evidence.
3. Build a SemGEM catalogue from the remaining model structure and annotations.
4. Enrich using pinned MNXref 4.5 and current Rhea cross-references.
5. Query KEGG at runtime and retain the result only in the local catalogue.
6. Compare accepted pathway concepts with canonicalized reference labels.

Two pathway measures are kept separate:

- whole-model pathway coverage: pathway-assigned reactions / all reactions;
- reference pathway recall: correctly assigned reactions / reactions carrying
  a supported curated pathway label.

## Baselines and first development pass

| Stage | Supported reference labels | Reference reactions | Whole-model pathway coverage | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Original vocabulary, static only | 48/147 | 2,067 | 2.1% | 29.0% | 0.4% | 0.009 |
| Original vocabulary, full providers | 48/147 | 2,067 | 14.2% | 55.4% | 47.5% | 0.511 |
| Expanded human vocabulary, full providers | 108/147 | 6,078 | 15.8% | 54.8% | 21.4% | 0.307 |
| First external-label alignment | 108/147 | 6,078 | 17.1% | 58.1% | 24.5% | 0.345 |
| Second vocabulary pass | 134/147 | 6,831 | 17.3% | 59.5% | 23.2% | 0.333 |
| Current label alignment | 134/147 | 6,831 | 17.5% | 59.6% | 23.4% | 0.336 |

Expanding the vocabulary makes the benchmark harder because thousands of
previously ignored curated pathway reactions enter the denominator. The first
48-label and current 134-label scores therefore must not be compared as if they
were evaluated against the same target set.

No evidence weights or thresholds were changed during this development pass.

## Examples of current pathway performance

| Canonical pathway | Reference reactions | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| Bile acid metabolism | 289 | 98.4% | 21.1% | 34.8% |
| Drug and xenobiotic metabolism | 730 | 100.0% | 16.2% | 27.8% |
| Glycosphingolipid metabolism | 124 | 70.5% | 69.4% | 69.9% |
| Glycolysis | 44 | 75.8% | 56.8% | 64.9% |
| Pentose phosphate pathway | 26 | 72.0% | 69.2% | 70.6% |
| Inositol phosphate metabolism | 93 | 93.1% | 58.1% | 71.5% |
| tRNA charging | 21 | 100.0% | 100.0% | 100.0% |

The current build also begins to recognize glycosaminoglycan and O-glycan
pathways after aligning their canonical labels with provider terminology.

## Hierarchical development pass

The canonical vocabulary now represents pathway parents explicitly. Accepted
narrow conclusions materialize their broader ancestors; broad evidence never
invents a narrower child. The benchmark reports exact/specific recovery and
broad-only compatible recovery separately.

The first hierarchy-aware development pass used runtime KEGG evidence plus
transferable semantic anchors in reaction names and participating metabolite
names. No Human-GEM `MAR` identifiers or reaction-membership lists were added
to the package.

| Human-GEM measure | Result |
|---|---:|
| Eligible curated pathway reactions | 6,831 |
| Exact/specific reactions recovered | 3,478 (50.91%) |
| Broad-only compatible reactions | 2,126 (31.12%) |
| Hierarchy-compatible reactions | 5,604 (82.04%) |
| Reactions receiving any pathway conclusion | 8,317/12,931 (64.32%) |
| Strict pair precision | 56.14% |
| Strict pair recall | 50.91% |
| Strict pair F1 | 53.40% |

The 82.04% result meets the provisional development coverage target, but it is
not equivalent to 82.04% exact pathway classification. A second conservative
specificity pass converted part of the broad-only component into exact
assignments using transferable pharmacokinetic, N-glycan, and fatty-acid
chemistry signals. Candidate peptide and aromatic-amino-acid fragments were
rejected after they increased recall at unacceptable precision cost.

As an initial regression check, the unchanged 118-pair curated benchmark over
*E. coli* core, iJO1366, iJN678, and iMM904 produced 99.05% precision, 88.14%
recall, and 93.27% F1 without subsystem or KEGG evidence. This small benchmark
does not test the new broad families comprehensively and remains a development
check rather than final independent validation.

A subsystem-free, provider-free portability run over the 20 structurally valid
local models contained 54,062 reactions. Static model evidence assigned at
least one pathway (including inherited broad parents) to 27,559 reactions,
giving 50.98% pathway coverage. Excluding SBO and subsystem evidence, 38,157
reactions (70.58%) received some portable semantic conclusion. These are
coverage figures, not accuracy estimates; inherited ancestors also make them
incomparable with older flat-vocabulary pathway-coverage reports.

## Important finding: pathway granularity

Human-GEM, KEGG, and SemGEM do not always describe pathways at the same level.
Examples include:

- Human-GEM `Carnitine shuttle` reactions linked by KEGG to the broader
  `Fatty acid degradation` pathway;
- Human-GEM `Cholesterol metabolism` reactions linked to `Steroid
  biosynthesis`;
- Human-GEM `Biopterin metabolism` reactions linked to `Folate biosynthesis`;
- Human-GEM `Lysine metabolism` reactions divided by external resources into
  lysine biosynthesis and degradation.

These are not necessarily biologically incorrect predictions. Strict exact
label matching counts them as errors because the current concept system is
flat. A parent/child pathway hierarchy and a separate hierarchical metric are
therefore the next important design decision. Strict precision and recall must
remain available alongside it.

## Next human-development work

1. Improve exact/specific pathway recovery while monitoring precision; do not
   treat broad-only compatibility as an exact result.
2. Investigate the remaining drug/xenobiotic reactions using a redistributable
   ontology or runtime provider rather than embedding a Human-GEM drug list.
3. Add only general biological mappings; do not encode `MAR` reaction IDs or
   copy Human-GEM reaction membership into SemGEM.
4. Perform provider and semantic-anchor ablations.
5. Evaluate confidence thresholds only after the vocabulary and hierarchy are
   stable.
6. Re-run the previous multi-model cohort and add hierarchy-aware per-model
   reporting.
7. Then repeat the controlled workflow for bacterial, yeast, and
   photosynthetic development models before freezing an independent holdout.
