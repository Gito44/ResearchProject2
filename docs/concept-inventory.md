# SemGEM concept inventory

This document records the provisional v0.5.1 concept expansion and the evidence
observed during development. It is an engineering smoke evaluation, not the
final biological validation required for the thesis.

## Evidence sources inspected

The following four local models were evaluated without KEGG network
enrichment:

- Recon3D
- *E. coli* core
- iJO1366
- iYS1720 (the model stored in `salmonella.xml.gz`)

Together they contain 16,635 reactions. Their annotations include SBO, KEGG,
BiGG, MetaNetX, Rhea, Reactome, ChEBI, BioCyc, and other model-specific
sources. SBO and model subsystem labels are the active redistributable
enrichment sources in this evaluation.

The reaction-level SBO terms observed were:

| SBO term | Label | Annotated reactions |
|---|---|---:|
| SBO:0000176 | biochemical reaction | 6,446 |
| SBO:0000185 | translocation reaction | 5,213 |
| SBO:0000627 | exchange reaction | 2,376 |
| SBO:0000375 | process | 2,250 |
| SBO:0000628 | demand reaction | 164 |
| SBO:0000632 | sink reaction | 101 |
| SBO:0000629 | biomass production | 10 |
| SBO:0000630 | ATP maintenance | 1 |

The generic `process` term is retained as provider information but is not
currently mapped to a user-facing concept because it does not add enough
meaning for model navigation.

## Provisional concept groups

The v0.5.1 vocabulary contains 84 canonical concepts:

- objectives: model objective, biomass production, and ATP maintenance;
- reaction types: biochemical, translocation, exchange, demand, and sink;
- specific exchanges: oxygen, carbon dioxide, glucose, acetate, ammonium,
  nitrate, phosphate, sulfate, and photons;
- central, energy, lipid, nucleotide, carbohydrate, vitamin/cofactor,
  amino-acid, cell-envelope, and photosynthesis-related pathways.

Provider-independent preferred labels and synonyms are stored in
`semgem/resources/concepts.toml`. Exact normalized labels can therefore connect
model subsystem labels, SBO labels, and runtime KEGG pathway labels to the same
canonical concept.

## Conservative model evidence

Model-ID evidence is restricted to established boundary-reaction conventions:

- `DM_` for demand reactions;
- `SK_` for sink reactions;
- `ATPM` for ATP maintenance;
- `EX_` plus a metabolite token for selected exchange concepts.

Token-aware matching is used so that, for example, `DMATT` is not treated as a
demand reaction, `SKMtex` is not treated as a sink, and `CO2t` is not treated as
an exchange reaction.

Broad free-text transport matching is intentionally excluded. Exact subsystem
labels such as `Transport, Inner Membrane` are accepted, while terms such as
electron transport are not automatically assumed to represent translocation.

## Four-model smoke results

The no-KEGG run produced 16,458 semantic assignments after the concept
expansion. Important checks included:

- one oxygen, carbon-dioxide, glucose, acetate, ammonium, and phosphate
  exchange was identified in each model;
- nitrate exchange was present in iJO1366 and iYS1720;
- sulfate exchange was present in Recon3D, iJO1366, and iYS1720;
- exactly one ATP-maintenance reaction was identified in each model;
- all `DM_` and `SK_` assignments matched the strict prefixes in the inspected
  models;
- iJO1366 exact subsystem assignments reproduced their source subsystem sizes;
- no photon or photosynthesis concepts were assigned because the current test
  set contains no photosynthetic model.

The pathway counts currently demonstrate extraction and normalization, not
ground-truth accuracy. Models without useful subsystem labels will depend more
heavily on runtime KEGG enrichment or future providers.

### Reaction-level coverage

The following table distinguishes source availability from successful semantic
conclusions. `SBO conclusion` means that at least one accepted concept for the
reaction is supported by SBO evidence. `Any conclusion` also includes strict
model conventions and subsystem evidence.

| Model | Reactions | Subsystem | SBO annotation | KEGG annotation | SBO conclusion | Any conclusion |
|---|---:|---:|---:|---:|---:|---:|
| Recon3D | 10,600 | 0 | 10,600 | 896 | 10,600 | 10,600 |
| *E. coli* core | 95 | 0 | 21 | 0 | 21 | 22 |
| iJO1366 | 2,583 | 2,251 | 2,583 | 755 | 333 | 2,444 |
| iYS1720 | 3,357 | 0 | 3,357 | 749 | 3,357 | 3,357 |

These totals must be interpreted by semantic depth. For example, many SBO
conclusions identify a reaction type such as biochemical, exchange, demand, or
sink; they do not necessarily provide pathway membership. In the no-KEGG run,
iJO1366 received pathway concepts for 1,463 reactions because it has extensive
model subsystem labels. The other three models received no pathway concepts
from their source subsystems.

## Full iJO1366 runtime KEGG check

The complete set of 741 unique KEGG reaction identifiers in iJO1366 was
resolved through KEGG REST during development. All identifiers resolved
without provider warnings. The run took approximately 20 minutes at the
provider rate limit, demonstrating both the value of catalog-level reuse and
the performance cost of a cold KEGG run.

With the initial 73-concept evaluation vocabulary:

- 653 of the 755 reactions carrying KEGG annotations received at least one
  KEGG-backed canonical pathway concept (approximately 86.5%);
- 3,294 total semantic assignments were accepted after combining model, SBO,
  and KEGG evidence;
- 1,477 distinct reactions received at least one pathway concept;
- 1,463 of those pathway-classified reactions had model-subsystem support for
  at least one accepted pathway concept.

Inspection of specific unmapped KEGG labels then justified 11 additional
concepts, including pentose/glucuronate interconversions, methane metabolism,
aromatic-compound degradation, ascorbate/aldarate metabolism,
D-amino-acid metabolism, ubiquinone biosynthesis, and branched-chain
amino-acid degradation. Broad aggregate maps were still excluded.

After rescoring the stored provider results with the 84-concept vocabulary:

- 682 of the 755 KEGG-annotated reactions received a KEGG-backed canonical
  concept (approximately 90.3%);
- accepted assignments increased from 3,294 to 3,409;
- the new concepts contributed 115 assignments without requiring another
  network request.

For iJO1366, KEGG increased pathway-classified reactions from 1,463 to 1,479
and total reactions with any semantic conclusion from 2,444 to 2,459. Its
larger contribution was semantic depth: pathway assignments increased from
1,463 to 2,419 because KEGG supplied additional and overlapping pathway
memberships. This distinction is important when evaluating usefulness:
coverage alone understates the extra navigation and cross-source evidence.

The returned labels demonstrated:

- exact glycolysis and pyruvate-metabolism matches;
- the KEGG label `Citrate cycle (TCA cycle)`, which was added as a TCA synonym;
- legitimate multi-label membership of aconitase in TCA, glyoxylate metabolism,
  and other carbon-fixation pathways;
- broad labels such as `Metabolic pathways`, which remain deliberately
  unmapped because they do not make the model substantially easier to browse.

Broad labels such as `Metabolic pathways`, `Biosynthesis of secondary
metabolites`, and `Microbial metabolism in diverse environments` remain
deliberately unmapped because they do not provide sufficiently specific
navigation.

## Provider disagreement inspection

KEGG pathway membership and model subsystems often use different, overlapping
boundaries. SemGEM therefore permits multiple pathway concepts rather than
forcing one exclusive classification.

Examples inspected in iJO1366 included:

- KEGG placed acetyl-CoA synthetase and alcohol dehydrogenase in
  glycolysis/gluconeogenesis, while the model used pyruvate metabolism;
- KEGG placed phosphoenolpyruvate carboxykinase in both
  glycolysis/gluconeogenesis and the TCA-cycle map, while the model used
  anaplerotic reactions;
- KEGG placed fructose-bisphosphate aldolase in the pentose-phosphate map,
  while the model used glycolysis/gluconeogenesis;
- several model-curated glycolysis, TCA, and pentose-phosphate reactions had no
  corresponding KEGG-backed conclusion, commonly because the reaction lacked
  a usable KEGG annotation or the provider used a different pathway boundary.

These are not treated automatically as false positives or false negatives.
The final thesis evaluation requires a manually curated reference sample.

## Provisional scoring calibration

The current v0.5.1 scores are evidence-strength ranks, not probabilities:

| Evidence | Weight | Current role |
|---|---:|---|
| objective coefficient | 1.00 | decisive |
| direct SBO term | 0.95 | strong ontology evidence |
| strict model identifier convention | 0.95 | strong convention evidence |
| KEGG pathway label | 0.90 | strong provider evidence |
| exact model subsystem | 0.80 | accepted curated model evidence |
| exact model entity name | 0.70 | supporting evidence only |
| SBO ancestor | 0.55 | supporting hierarchical evidence |
| broad exchange text | 0.40 | weak supporting evidence |

The default threshold is 0.75. Consequently, an exact reaction name alone
does not create a semantic conclusion, while a direct SBO term, strict
identifier convention, KEGG pathway relation, or exact subsystem can. The
four-model model/SBO assignment count remained unchanged after this
calibration, indicating that confidence tiers changed without unexpectedly
removing the established high-confidence conclusions.

## Required later evaluation

Before v1, the thesis evaluation must:

- manually establish expected concepts for a representative reaction sample;
- measure precision, recall, false positives, and false negatives;
- compare model-only, SBO, and SBO-plus-KEGG modes;
- include at least one photosynthetic model;
- validate or revise all provisional evidence weights and thresholds against
  the curated reference sample;
- inspect provider disagreements and reactions without conclusions.

## Additional-model evaluation

Three additional models were downloaded from the official BiGGr/BiGG service
for local research evaluation:

- iJN678, a photosynthetic *Synechocystis* model;
- iMM904, a *Saccharomyces cerevisiae* model;
- iYO844, a *Bacillus subtilis* model.

The files are excluded from Git and are not distributed with SemGEM.

| Model | Reactions | Reactions with subsystem | SBO annotations | Reactions with any conclusion | Pathway-classified reactions |
|---|---:|---:|---:|---:|---:|
| iJN678 | 863 | 863 | 863 | 863 | 553 |
| iMM904 | 1,577 | 1,576 | 1,577 | 1,577 | 733 |
| iYO844 | 1,250 | 1,249 | 1,250 | 1,250 | 0 |

This test exposed encoded subsystem labels in some BiGG-style SBML files, such
as `S_Fatty_Acid__Biosynthesis` and `S_GlycolysisGluconeogenesis`. A
conservative normalization fallback now decodes only labels with the explicit
`S_` prefix. This increased iMM904 pathway coverage from zero to 733 reactions.
The fallback is regression-tested and is not applied as general fuzzy
matching.

iYO844 remained without pathway conclusions because its subsystem vocabulary
uses very broad categories such as carbohydrates, lipids, amino acids, and
coenzymes. These categories are intentionally not converted into specific
pathway conclusions.

The photosynthetic iJN678 model exercised concepts absent from the original
test set:

| Concept | Assignments |
|---|---:|
| Photosynthesis | 13 |
| Carbon fixation | 6 |
| Porphyrin and chlorophyll metabolism | 48 |
| Carotenoid biosynthesis | 13 |
| Photon exchange | 1 |

The current BiGGr exports supplied SBO, BiGGr, and Rhea reaction annotations
but no KEGG reaction annotations. Consequently, optional KEGG enrichment cannot
improve these particular files without an additional cross-reference provider.
This makes Rhea or another redistributable identity bridge a stronger
post-SBO/KEGG candidate.
