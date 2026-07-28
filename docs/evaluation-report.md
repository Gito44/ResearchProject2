# SemGEM provisional evaluation report

This document records the reproducible engineering and biological evaluation
performed for the provisional v0.5.1 implementation. It is not the final thesis
results chapter. The manually curated benchmark should receive independent
biological review before its results are treated as definitive.

## Questions

The evaluation asks:

1. Does SemGEM reduce model-specific work?
2. How accurately does it recover manually curated reaction concepts?
3. How consistently does it process a diverse multi-model cohort?
4. What are its current precision, recall, runtime, and coverage?
5. Do the evidence weights and thresholds require further adjustment?

## Curated benchmark

`evaluation/curated_benchmark.toml` contains 118 reaction/concept pairs across:

- *E. coli* core;
- iJO1366;
- photosynthetic iJN678; and
- yeast iMM904.

The benchmark covers glycolysis, pentose-phosphate metabolism, the TCA cycle,
photosynthesis, carbon fixation, oxygen/carbon-dioxide/glucose/photon
exchanges, and ATP maintenance. Ambiguous pathway-boundary reactions are
excluded where possible.

The benchmark is closed-world only for its listed reactions and concepts. It
does not imply that reactions have no valid memberships outside that scope.

### Default offline pathway-focused result

| System | Precision (95% CI) | Recall (95% CI) | F1 | TP | FP | FN |
|---|---:|---:|---:|---:|---:|---:|
| Portable exact-label baseline | 1.000 (0.875–1.000) | 0.229 (0.162–0.312) | 0.372 | 27 | 0 | 91 |
| SemGEM | 1.000 (0.960–1.000) | 0.788 (0.706–0.852) | 0.882 | 93 | 0 | 25 |

SemGEM recovered 66 more curated pairs than the generic exact-label baseline.
The remaining false negatives were 24 pathway memberships in the minimally
annotated *E. coli* core model and one yeast TCA-cycle membership (`MDHi2`).

Per-model SemGEM recall was:

| Model | Precision | Recall | F1 |
|---|---:|---:|---:|
| *E. coli* core | 1.000 | 0.143 | 0.250 |
| iJO1366 | 1.000 | 1.000 | 1.000 |
| iJN678 | 1.000 | 1.000 | 1.000 |
| iMM904 | 1.000 | 0.958 | 0.979 |

This result supports the claim that SemGEM reduces terminology-specific work,
but also demonstrates that it cannot recover missing pathway semantics from a
model with no suitable identity or pathway annotations.

An explicit source-ablation run using
`evaluation.evaluate_benchmark --exclude-source sbo` produced the identical
result (precision 1.000, recall 0.788, F1 0.882). SBO evidence contributed to
one scoped ATP-maintenance conclusion, but that conclusion also had sufficient
model evidence. Broad SBO reaction typing therefore does not inflate this
pathway/exchange/objective benchmark.

### Runtime KEGG result

Reusing the complete iJO1366 KEGG provider results changed the strict benchmark
result to:

| Precision (95% CI) | Recall (95% CI) | F1 | TP | FP | FN |
|---:|---:|---:|---:|---:|---:|
| 0.886 (0.811–0.933) | 0.788 (0.706–0.852) | 0.834 | 93 | 12 | 25 |

All 12 additional predictions came from iJO1366 reference-map memberships.
Eleven were carbon-fixation labels and one was pentose-phosphate membership.
KEGG legitimately places shared reactions on these reference maps, but a strict
model-local benchmark does not necessarily consider the organism to perform
the whole pathway.

This reveals two distinct semantics:

1. a reaction is present on an external reference pathway map; and
2. the reaction serves that pathway as a model-local functional module.

Evidence weights cannot resolve this distinction. SemGEM should preserve the
provider assertion and eventually expose query policies for reference
membership, model-local membership, and cross-source consensus.

## Reduction in model-specific work

The benchmark models represented the same canonical concepts using at least
nine observed subsystem forms, including:

- `Glycolysis/Gluconeogenesis`;
- `S_GlycolysisGluconeogenesis`;
- `Pentose Phosphate Pathway`;
- `Pentose phosphate pathway`;
- `S_Pentose_Phosphate_Pathway`;
- `Citric Acid Cycle`;
- `Citrate cycle (TCA cycle)`; and
- `S_Citric_Acid_Cycle`.

A developer implementing these queries directly would need model-specific
aliases and decoding rules and would still obtain no pathway result from
*E. coli* core. SemGEM exposes stable canonical identifiers instead.

The portable baseline F1 of 0.372 versus SemGEM's 0.882 is the current
quantitative proxy for reduced model-specific work. A later user study or timed
developer task would provide stronger human-effort evidence.

## Sixteen-model cohort

Eighteen local files were attempted. Sixteen valid models were imported into
one catalog; two current repository exports were rejected because their SBML
model IDs were empty. SemGEM does not silently invent model identities.

The valid cohort contained:

- 16 models;
- 37,017 reactions;
- 36,943 reactions with SBO annotations;
- 5,939 reactions with nonempty subsystem labels;
- 2,400 reactions with KEGG annotations;
- 36,805 reactions with at least one semantic conclusion; and
- 2,749 reactions with at least one pathway conclusion.

Overall reaction-level semantic coverage was 99.4%, but pathway coverage was
only 7.4%. The difference is essential: broad SBO reaction-type conclusions
should not be mistaken for pathway interpretation.

| Model | Reactions | Subsystem reactions | Any semantic conclusion | Pathway conclusion |
|---|---:|---:|---:|---:|
| GCF_000167875_2 | 2,732 | 0 | 2,732 | 0 |
| GCF_000967155_2 | 2,732 | 0 | 2,732 | 0 |
| GCF_002079545_1 | 1,243 | 0 | 1,243 | 0 |
| GCF_003053245_1 | 1,125 | 0 | 1,125 | 0 |
| GCF_019456065_1 | 1,064 | 0 | 1,064 | 0 |
| Recon3D | 10,600 | 0 | 10,600 | 0 |
| *E. coli* core | 95 | 0 | 22 | 0 |
| iAM_Pf480 | 1,083 | 0 | 1,083 | 0 |
| iCN900 | 1,230 | 0 | 1,230 | 0 |
| iEC1364_W | 2,771 | 0 | 2,771 | 0 |
| iJN678 | 863 | 863 | 863 | 553 |
| iJO1366 | 2,583 | 2,251 | 2,444 | 1,463 |
| iML1515 | 2,712 | 0 | 2,712 | 0 |
| iMM904 | 1,577 | 1,576 | 1,577 | 733 |
| iYO844 | 1,250 | 1,249 | 1,250 | 0 |
| iYS1720 | 3,357 | 0 | 3,357 | 0 |

Only iJN678, iJO1366, and iMM904 produced substantial pathway coverage from the
default offline workflow. Many recent BiGGr models supplied complete SBO
reaction typing but no pathway subsystems or KEGG reaction annotations.

Across the cohort, 16,613 reactions had BiGG identifiers, 10,375 had MetaNetX
reaction identifiers, and 7,730 had Rhea identifiers, compared with 2,400
carrying KEGG reaction identifiers. This provides quantitative support for
prioritizing a redistributable Rhea or MetaNetX identity bridge: it could reach
far more of the currently pathway-unclassified cohort than KEGG-only
enrichment.

## BioModels repository check

Three public BioModels GEMs outside the BiGG download workflow were imported:

| BioModels accession | Organism/model | Reactions | Subsystems | Reaction annotations | Pathway conclusions |
|---|---|---:|---:|---:|---:|
| MODEL1507180050 | *Pichia pastoris* PpaMBEL1254 | 1,254 | 0 | 0 | 0 |
| MODEL1507180060 | *E. coli* iJR904 | 1,075 | 0 | 0 | 0 |
| MODEL1507180064 | *Zea mays* iRS1563 | 1,785 | 0 | 0 | 0 |

The models still allowed limited convention-based conclusions: iJR904 yielded
exchange, objective, biomass, ATP-maintenance, and specific exchange concepts;
iRS1563 yielded exchange, objective, and biomass concepts; PpaMBEL1254 yielded
only its objective. None supplied the identity or pathway metadata required for
pathway recovery. This confirms that the missing-pathway problem is not only a
consequence of using BiGG-derived models.

MODEL1507180055 (mouse iMM1415) was also attempted, but COBRApy rejected a
metabolite identifier containing a vertical-tab control character. SemGEM did
not modify the repository model silently. This is an upstream
SBML/interoperability limitation to report separately from semantic coverage.

## Preliminary MetaNetX/Rhea bridge experiment

The v0.5.2 prototype resolves only model-relevant entries from user-supplied
official `reac_xref.tsv` and `rhea2xrefs.tsv` files. It does not bundle either
full dataset. On iJO1366:

- the original model contained 755 KEGG reaction annotations;
- MetaNetX/Rhea bridging exposed 821 distinct KEGG reaction identities;
- 1,085 MetaCyc and 499 Reactome reaction identities were also connected;
- the offline identity stage took approximately 7 seconds; and
- the batched runtime KEGG stage resolved 822 reaction identifiers in
  approximately 219 seconds.

Unique pathway-covered reactions rose from 1,463/2,583 (56.6%) to
1,480/2,583 (57.3%). The small unique-coverage gain is expected because iJO1366
already has extensive subsystem labels. The enriched catalog nevertheless
added substantially broader pathway assignments and independent external
support. Models without subsystem labels are required to measure the bridge's
main intended benefit.

On iYS1720, which has 3,357 reactions and no subsystem labels, the full bridge
plus runtime pathway workflow increased unique pathway coverage from zero to
738 reactions (22.0%). This demonstrates a substantial coverage gain in the
target missing-subsystem case. Direct KEGG annotations supported 676 of those
reactions (20.1% of the model); MetaNetX/Rhea bridging added 62 reactions with
pathway conclusions that had no direct KEGG or model evidence, raising coverage
by 1.9 percentage points. The larger value of the bridges in this model is
cross-checking: MetaNetX supported 737 pathway-covered reactions and Rhea
supported 603.

These figures do not establish model-local accuracy:
reference pathway maps include shared reactions and produced potentially broad
labels such as carbon fixation. The curated benchmark must therefore evaluate
provider-derived memberships separately from raw coverage.

Provider-specific evidence remains separate after scoring. Of the stored
pathway conclusions, 1,245 in iJO1366 and 1,241 in iYS1720 had support from at
least two of model, direct KEGG, MetaNetX-bridged, or Rhea-bridged evidence.
This makes later agreement and consensus analysis possible. The provisional
v0.5.2 scorer currently accepts either identity bridge at weight 0.85; whether
agreement should alter confidence remains an evaluation question.

## Performance

The 16-model offline build produced a roughly 62 MB SQLite catalog.

| Operation | Result |
|---|---:|
| Complete build | 58.55 seconds |
| Candidate evidence evaluated | 49,025 |
| Semantic assignments stored | 38,243 |
| Cross-model `glycolysis` search | 0.79 seconds |
| Single-entity concept query | 0.51 seconds |

CLI startup contributes to the small query timings. The catalog remains usable
at this scale, but profiling and batched database insertion are justified
before substantially larger collections.

The complete cold iJO1366 KEGG run took approximately 20 minutes at the
provider rate limit. Shared external relationships avoid repeating those
requests within one catalog.

## Threshold and weight sensitivity

The curated model/SBO candidates were rescored at thresholds from 0.50 to 1.00.

| Threshold range | Precision | Recall | F1 |
|---|---:|---:|---:|
| 0.50–0.80 | 1.000 | 0.788 | 0.882 |
| 0.85–0.95 | 1.000 | 0.136 | 0.239 |
| 1.00 | 1.000 | 0.085 | 0.156 |

The current default threshold of 0.75 lies on the stable plateau. Raising it
above the 0.80 subsystem weight removes most curated pathway conclusions.
Lowering it does not improve this benchmark because weak name evidence does
not occur for the missing *E. coli* pathway reactions.

The current ordering remains justified:

- objective coefficient: 1.00;
- direct SBO and strict identifier conventions: 0.95;
- KEGG reference pathway: 0.90;
- exact subsystem: 0.80;
- exact name: 0.70, supporting only;
- SBO ancestor: 0.55; and
- broad text evidence: 0.40.

No further numerical tuning is justified from this benchmark alone. The KEGG
precision issue is semantic-policy design, not a score-calibration issue.

## Conclusions

The current evidence supports these claims:

- SemGEM substantially improves portable semantic retrieval over one naive
  exact-label strategy.
- It handles several real terminology and encoding variants without
  model-specific application code.
- It is highly accurate on the curated concepts when models provide usable
  subsystems or strict conventions.
- It cannot infer missing pathway biology from unannotated reactions.
- SBO provides excellent structural coverage but limited pathway depth.
- KEGG greatly increases reference pathway depth but can broaden membership
  beyond model-local biological roles.
- The multi-model SQLite design works for tens of thousands of reactions, with
  batching as the next clear scalability improvement.

## Required follow-up

Before final thesis reporting:

- have the curated benchmark independently reviewed;
- expand it with negatives selected before inspecting predictions;
- report confidence intervals or bootstrap uncertainty;
- evaluate provider-policy variants rather than treating all pathway semantics
  as identical;
- add a redistributable identity bridge such as Rhea or MetaNetX for models
  lacking KEGG identifiers;
- benchmark batched insertion if large-catalog performance becomes part of the
  thesis claim; and
- consider a small timed developer study if direct evidence of saved human
  effort is feasible.
