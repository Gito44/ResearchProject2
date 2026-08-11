# Detailed model coverage analysis

## Scope and interpretation

This report evaluates the current SemGEM development build on the complete
19-model cohort (41,131 reactions). The catalogue was rebuilt with the current
SBO, KEGG, Rhea, MetaNetX, and MetaNetX-chemistry providers.

Coverage is reported at two levels:

- **Any semantic coverage:** a reaction received at least one accepted
  conclusion, including broad reaction types such as biochemical reaction,
  transport, exchange, or a pathway assignment.
- **Pathway coverage:** a reaction received at least one accepted pathway
  conclusion. This is the more demanding and more relevant measure for queries
  such as “show glycolysis”.

An **allocation** is one accepted reaction–concept pair. A reaction may receive
multiple allocations, so allocation counts can exceed reaction counts.

The “without SBO” results are a true ablation: SBO-derived evidence is removed
before conclusions are rescored against their thresholds. They are not produced
by merely hiding SBO labels after classification.

The 95% confidence intervals below are Wilson intervals for observed coverage
proportions. They quantify sampling precision within this cohort, not biological
correctness. Similarly, SemGEM confidence scores are current rule scores and
must not yet be interpreted as calibrated probabilities.

## Executive summary

Across all 41,131 reactions:

| Scenario | Allocations | Covered reactions | Coverage | 95% CI | Pathway-covered reactions | Pathway coverage | 95% CI |
|---|---:|---:|---:|---:|---:|---:|---:|
| All evidence | 61,185 | 39,655 | 96.41% | 96.23–96.59% | 11,783 | 28.65% | 28.21–29.09% |
| Without SBO | 41,757 | 28,060 | 68.22% | 67.77–68.67% | 11,783 | 28.65% | 28.21–29.09% |
| Without model subsystems | 59,059 | 39,071 | 94.99% | 94.78–95.20% | 10,638 | 25.86% | 25.44–26.29% |
| Without SBO or model subsystems | 39,618 | 26,948 | 65.52% | 65.06–65.98% | 10,638 | 25.86% | 25.44–26.29% |
| Model-derived evidence only | 26,606 | 21,063 | 51.21% | 50.72–51.69% | 4,772 | 11.60% | 11.30–11.91% |
| SBO only | 34,693 | 34,693 | 84.35% | 84.00–84.70% | 0 | 0.00% | — |
| KEGG only | 6,798 | 3,908 | 9.50% | 9.23–9.79% | 3,908 | 9.50% | 9.23–9.79% |
| MetaNetX only | 16,137 | 8,784 | 21.36% | 20.96–21.76% | 8,784 | 21.36% | 20.96–21.76% |
| Rhea only | 10,280 | 5,282 | 12.84% | 12.52–13.17% | 5,282 | 12.84% | 12.52–13.17% |
| MetaNetX chemistry only | 6,890 | 3,478 | 8.46% | 8.19–8.73% | 3,478 | 8.46% | 8.19–8.73% |

The main finding is that the apparently excellent 96.4% general coverage is
partly caused by broad SBO classifications. SBO alone covers 84.3% of reactions
but produces no pathway assignments in the current concept system. Removing SBO
reduces general coverage by 28.2 percentage points, while pathway coverage is
unchanged. Therefore, pathway coverage and non-SBO coverage are the more useful
headline measures for SemGEM’s original purpose.

The current pathway coverage is 28.65%, up from 22.6% before metabolite
standardisation and chemistry-based inference: 2,500 additional reactions and
approximately 6.1 percentage points.

### Micro, macro, and median model coverage

The aggregate figures above are **micro-averages**: every reaction has equal
weight, so Recon3D contributes 25.8% of the cohort denominator. Macro-averages
give every model equal weight, while medians describe the typical model.

| Scenario | Micro coverage | Macro coverage | Median model coverage | Micro pathway coverage | Macro pathway coverage | Median model pathway coverage |
|---|---:|---:|---:|---:|---:|---:|
| All evidence | 96.4% | 94.2% | 100.0% | 28.6% | 34.6% | 29.7% |
| Without SBO | 68.2% | 67.7% | 70.0% | 28.6% | 34.6% | 29.7% |
| Without SBO or subsystems | 65.5% | 64.3% | 70.0% | 25.9% | 31.0% | 29.7% |
| KEGG only | 9.5% | 8.9% | 0.0% | 9.5% | 8.9% | 0.0% |
| MetaNetX only | 21.4% | 26.3% | 25.6% | 21.4% | 26.3% | 25.6% |
| Rhea only | 12.8% | 13.4% | 18.1% | 12.8% | 13.4% | 18.1% |

The macro pathway estimate is higher than the micro estimate because the large
Recon3D model has only 14.4% pathway coverage. KEGG’s median of zero shows that
it is highly valuable in some models but absent from more than half the cohort.
MetaNetX currently has the most consistent cross-model reach.

## Per-model coverage

| Model | Reactions | Allocations, all | Covered, all | Coverage, all | Allocations, no SBO | Covered, no SBO | Coverage, no SBO | Pathway-covered | Pathway coverage |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GCF_000167875_2_json | 2,732 | 4,082 | 2,732 | 100.0% | 2,482 | 1,930 | 70.6% | 801 | 29.3% |
| GCF_000967155_2_json | 2,732 | 4,082 | 2,732 | 100.0% | 2,482 | 1,930 | 70.6% | 801 | 29.3% |
| GCF_002079545_1_json | 1,243 | 1,335 | 1,243 | 100.0% | 461 | 442 | 35.6% | 73 | 5.9% |
| GCF_003053245_1_json | 1,125 | 1,214 | 1,125 | 100.0% | 463 | 441 | 39.2% | 67 | 6.0% |
| GCF_019456065_1 | 1,064 | 1,151 | 1,064 | 100.0% | 434 | 415 | 39.0% | 68 | 6.4% |
| MODEL1507180050 | 1,254 | 1,187 | 716 | 57.1% | 1,187 | 716 | 57.1% | 716 | 57.1% |
| MODEL1507180060 | 1,075 | 1,219 | 782 | 72.7% | 1,219 | 782 | 72.7% | 454 | 42.2% |
| MODEL1507180064 | 1,785 | 1,892 | 1,198 | 67.1% | 1,892 | 1,198 | 67.1% | 1,102 | 61.7% |
| Recon3D | 10,600 | 16,672 | 10,600 | 100.0% | 12,076 | 7,418 | 70.0% | 1,524 | 14.4% |
| e_coli_core | 95 | 199 | 91 | 95.8% | 199 | 91 | 95.8% | 47 | 49.5% |
| iAM_Pf480 | 1,083 | 1,922 | 1,083 | 100.0% | 1,220 | 698 | 64.5% | 322 | 29.7% |
| iCN900 | 1,230 | 2,175 | 1,230 | 100.0% | 1,219 | 732 | 59.5% | 458 | 37.2% |
| iEC1364_W | 2,771 | 2,985 | 2,771 | 100.0% | 1,329 | 1,305 | 47.1% | 192 | 6.9% |
| iJN678 | 863 | 2,013 | 863 | 100.0% | 1,335 | 801 | 92.8% | 632 | 73.2% |
| iJO1366 | 2,583 | 4,060 | 2,529 | 97.9% | 4,059 | 2,528 | 97.9% | 1,483 | 57.4% |
| iML1515 | 2,712 | 4,060 | 2,712 | 100.0% | 2,481 | 1,929 | 71.1% | 799 | 29.5% |
| iMM904 | 1,577 | 3,431 | 1,577 | 100.0% | 2,416 | 1,468 | 93.1% | 928 | 58.8% |
| iYO844 | 1,250 | 2,143 | 1,250 | 100.0% | 1,374 | 932 | 74.6% | 451 | 36.1% |
| iYS1720 | 3,357 | 5,363 | 3,357 | 100.0% | 3,429 | 2,304 | 68.6% | 865 | 25.8% |

## Per-model statistical detail

| Model | Non-SBO coverage (95% CI) | Pathway coverage (95% CI) | Mean accepted score | Allocations per non-SBO-covered reaction |
|---|---:|---:|---:|---:|
| GCF_000167875_2_json | 70.6% (68.9–72.3) | 29.3% (27.6–31.1) | 0.971 | 1.49 |
| GCF_000967155_2_json | 70.6% (68.9–72.3) | 29.3% (27.6–31.1) | 0.971 | 1.49 |
| GCF_002079545_1_json | 35.6% (32.9–38.3) | 5.9% (4.7–7.3) | 0.959 | 1.07 |
| GCF_003053245_1_json | 39.2% (36.4–42.1) | 6.0% (4.7–7.5) | 0.961 | 1.08 |
| GCF_019456065_1 | 39.0% (36.1–42.0) | 6.4% (5.1–8.0) | 0.960 | 1.08 |
| MODEL1507180050 | 57.1% (54.3–59.8) | 57.1% (54.3–59.8) | 0.996 | 1.66 |
| MODEL1507180060 | 72.7% (70.0–75.3) | 42.2% (39.3–45.2) | 0.924 | 1.56 |
| MODEL1507180064 | 67.1% (64.9–69.3) | 61.7% (59.5–64.0) | 0.992 | 1.58 |
| Recon3D | 70.0% (69.1–70.8) | 14.4% (13.7–15.1) | 0.967 | 1.57 |
| e_coli_core | 95.8% (89.7–98.4) | 49.5% (39.6–59.4) | 0.922 | 2.19 |
| iAM_Pf480 | 64.5% (61.6–67.2) | 29.7% (27.1–32.5) | 0.969 | 1.77 |
| iCN900 | 59.5% (56.7–62.2) | 37.2% (34.6–40.0) | 0.973 | 1.77 |
| iEC1364_W | 47.1% (45.2–49.0) | 6.9% (6.0–7.9) | 0.963 | 1.08 |
| iJN678 | 92.8% (90.9–94.4) | 73.2% (70.2–76.1) | 0.956 | 2.33 |
| iJO1366 | 97.9% (97.2–98.4) | 57.4% (55.5–59.3) | 0.938 | 1.61 |
| iML1515 | 71.1% (69.4–72.8) | 29.5% (27.8–31.2) | 0.971 | 1.50 |
| iMM904 | 93.1% (91.7–94.2) | 58.8% (56.4–61.3) | 0.941 | 2.18 |
| iYO844 | 74.6% (72.1–76.9) | 36.1% (33.5–38.8) | 0.977 | 1.71 |
| iYS1720 | 68.6% (67.0–70.2) | 25.8% (24.3–27.3) | 0.972 | 1.60 |

The high mean scores indicate that accepted conclusions usually cross the
current thresholds strongly. They do not demonstrate that those thresholds are
well calibrated; that requires independent biological validation.

## Provider contribution to pathway coverage

Provider-only columns show what each provider can conclude in isolation.
They overlap and must not be added together. “Portable combined” removes both
SBO and original subsystem labels while retaining static inference and all
external providers.

| Model | Model-only | KEGG-only | MetaNetX-only | Rhea-only | Chemistry-only | Portable combined |
|---|---:|---:|---:|---:|---:|---:|
| GCF_000167875_2_json | 6.7% | 0.0% | 23.6% | 19.8% | 11.8% | 29.3% |
| GCF_000967155_2_json | 6.7% | 0.0% | 23.6% | 19.8% | 11.8% | 29.3% |
| GCF_002079545_1_json | 5.0% | 0.0% | 0.9% | 0.8% | 0.2% | 5.9% |
| GCF_003053245_1_json | 4.8% | 0.0% | 1.2% | 1.0% | 0.2% | 6.0% |
| GCF_019456065_1 | 5.3% | 0.0% | 1.1% | 0.9% | 0.2% | 6.4% |
| MODEL1507180050 | 0.0% | 56.5% | 56.4% | 0.0% | 0.0% | 57.1% |
| MODEL1507180060 | 4.5% | 0.0% | 38.8% | 0.0% | 16.5% | 42.2% |
| MODEL1507180064 | 3.2% | 59.0% | 59.5% | 0.0% | 22.3% | 61.7% |
| Recon3D | 4.9% | 7.3% | 10.1% | 6.4% | 3.3% | 14.4% |
| e_coli_core | 27.4% | 0.0% | 41.1% | 0.0% | 5.3% | 49.5% |
| iAM_Pf480 | 6.6% | 0.0% | 25.6% | 22.0% | 14.5% | 29.7% |
| iCN900 | 3.6% | 0.0% | 35.8% | 31.0% | 21.7% | 37.2% |
| iEC1364_W | 6.1% | 0.0% | 0.9% | 0.7% | 0.3% | 6.9% |
| iJN678 | 68.1% | 0.1% | 39.9% | 34.8% | 23.3% | 52.7% |
| iJO1366 | 56.8% | 26.6% | 29.0% | 23.5% | 6.5% | 33.8% |
| iML1515 | 6.7% | 0.0% | 23.7% | 19.9% | 11.8% | 29.5% |
| iMM904 | 53.6% | 0.0% | 32.4% | 27.5% | 18.8% | 36.1% |
| iYO844 | 3.0% | 0.0% | 34.8% | 29.5% | 20.2% | 36.1% |
| iYS1720 | 5.2% | 20.2% | 22.2% | 18.1% | 6.9% | 25.8% |

MetaNetX currently contributes the broadest provider-only pathway coverage
(21.36% cohort-wide), followed by Rhea (12.84%), KEGG (9.50%), and
MetaNetX chemistry (8.46%). This ranking reflects both provider capability and
the identifiers present in this particular cohort. It is not a general ranking
of database quality.

## Annotation and metabolite-standardisation context

| Model | KEGG reaction refs | MetaNetX refs | Rhea refs | BiGG-like IDs | Standardised metabolites | Metabolite standardisation | Chemistry-matched reactions |
|---|---:|---:|---:|---:|---:|---:|---:|
| GCF_000167875_2_json | 0 | 0 | 790 | 2,732 | 1,274/1,941 | 65.6% | 420 |
| GCF_000967155_2_json | 0 | 0 | 790 | 2,732 | 1,274/1,942 | 65.6% | 420 |
| GCF_002079545_1_json | 0 | 0 | 12 | 1,243 | 256/1,251 | 20.5% | 4 |
| GCF_003053245_1_json | 0 | 0 | 12 | 1,125 | 246/1,130 | 21.8% | 5 |
| GCF_019456065_1 | 0 | 0 | 11 | 1,064 | 231/1,107 | 20.9% | 5 |
| MODEL1507180050 | 0 | 0 | 0 | 0 | 3/1,058 | 0.3% | 0 |
| MODEL1507180060 | 0 | 0 | 0 | 0 | 653/761 | 85.8% | 259 |
| MODEL1507180064 | 0 | 0 | 0 | 0 | 1,979/2,087 | 94.8% | 633 |
| Recon3D | 896 | 5,478 | 1,072 | 10,600 | 5,352/5,835 | 91.7% | 1,123 |
| e_coli_core | 0 | 0 | 0 | 95 | 42/72 | 58.3% | 5 |
| iAM_Pf480 | 0 | 0 | 291 | 1,083 | 577/909 | 63.5% | 185 |
| iCN900 | 0 | 0 | 441 | 1,230 | 564/885 | 63.7% | 334 |
| iEC1364_W | 0 | 0 | 26 | 2,771 | 431/1,933 | 22.3% | 12 |
| iJN678 | 0 | 0 | 337 | 863 | 514/795 | 64.7% | 234 |
| iJO1366 | 755 | 2,248 | 1,070 | 2,561 | 1,268/1,805 | 70.2% | 239 |
| iML1515 | 0 | 0 | 789 | 2,712 | 1,270/1,877 | 67.7% | 419 |
| iMM904 | 0 | 0 | 549 | 1,577 | 903/1,228 | 73.5% | 380 |
| iYO844 | 0 | 0 | 442 | 1,250 | 688/992 | 69.4% | 307 |
| iYS1720 | 749 | 2,649 | 1,098 | 3,357 | 1,932/2,436 | 79.3% | 331 |

This table helps explain the low-performing GCF models. The first pair contains
substantial Rhea linkage and moderate metabolite standardisation. The other
three have only 11–12 Rhea references, approximately 21% metabolite
standardisation, and almost no chemistry matches. SBO can still assign broad
reaction types, but there is little evidence from which SemGEM can infer
specific pathways.

## Accuracy evidence available so far

Coverage is not accuracy. Only five models currently have any curated
development reference:

### Curated concept benchmark

The small curated benchmark contains selected expected concepts for
`e_coli_core`, `iJN678`, `iJO1366`, and `iMM904`.

| Model | TP | FP | FN | Precision (95% CI) | Recall (95% CI) | F1 |
|---|---:|---:|---:|---:|---:|---:|
| e_coli_core | 28 | 10 | 0 | 0.737 (0.580–0.850) | 1.000 (0.879–1.000) | 0.848 |
| iJN678 | 38 | 8 | 0 | 0.826 (0.693–0.909) | 1.000 | 0.905 |
| iJO1366 | 28 | 15 | 0 | 0.651 (0.502–0.776) | 1.000 | 0.789 |
| iMM904 | 24 | 7 | 0 | 0.774 (0.602–0.886) | 1.000 | 0.873 |
| **Combined** | **118** | **40** | **0** | **0.747 (0.674–0.808)** | **1.000 (0.969–1.000)** | **0.855** |

Removing SBO does not change this selected benchmark because its expected
concepts are pathway/transport concepts rather than SBO-only broad types.
However, this benchmark is small, was used during development, and is not an
independent test set. Its perfect observed recall should therefore not be
generalised.

### iRC1080 subsystem benchmark

With source subsystem labels hidden, SemGEM assigns a comparable subsystem to
1,603 of 2,191 reactions (73.16% coverage). On comparable labels:

- Precision: 0.818
- Recall: 0.693
- F1: 0.751
- Pathway precision: 0.783
- Pathway recall: 0.616
- Pathway F1: 0.690
- Transport precision: 0.908
- Transport recall: 0.995

This is a useful development benchmark but is not independent: the model and
its terminology informed rule development. A held-out model or blinded manual
curation is still required for a defensible final accuracy claim.

## Individual model usefulness assessment

### GCF_000167875_2_json and GCF_000967155_2_json

Both models produce the same reaction-level semantic results. General coverage
falls from 100% with SBO to 70.6% without it, while pathway coverage is 29.3%.
MetaNetX and Rhea supply most pathway signal. SemGEM is moderately useful for
initial pathway browsing and reaction grouping despite the absence of subsystem
labels, but approximately 70% of reactions still lack pathway assignments.
The identical semantic results also show the need to treat duplicated or
closely related models carefully in cohort statistics.

### GCF_002079545_1_json

SBO creates 100% broad coverage, but non-SBO coverage is 35.6% and pathway
coverage only 5.9%. The model has almost no external reaction references and
only 20.5% metabolite standardisation. SemGEM is useful mainly for broad
reaction-type filtering; it does not yet provide a satisfactory pathway-level
view of this model.

### GCF_003053245_1_json

The pattern is similar: 39.2% non-SBO coverage and 6.0% pathway coverage.
SemGEM adds some searchable structure, but not enough to replace manual pathway
inspection. Improving identifier and metabolite normalisation for this model
family is likely more valuable than adding model-specific pathway rules.

### GCF_019456065_1

Non-SBO coverage is 39.0% and pathway coverage 6.4%. With only 11 Rhea
references and five chemistry-matched reactions, the evidence base is sparse.
Current usefulness is low for pathway research and moderate for broad
reaction-type exploration.

### MODEL1507180050

This model has no conventional annotation records, but its local reaction
identifiers can be interpreted as KEGG-style identities. SemGEM obtains 57.1%
pathway coverage. This is a strong demonstration of the intended value:
recovering biological organisation from identifiers even when explicit SBML
annotations are absent. The inferred identity convention must still be checked
biologically.

### MODEL1507180060

Non-SBO coverage is 72.7% and pathway coverage 42.2%. MetaNetX and
chemistry-based inference contribute substantially. SemGEM is useful for
building a first pathway browser or narrowing reactions for manual review,
though more than half the reactions remain without pathway assignments.

### MODEL1507180064

This is the strongest annotation-poor result: 61.7% pathway coverage, supported
by high metabolite standardisation (94.8%), KEGG-like identities, MetaNetX, and
chemistry inference. SemGEM is already highly useful for pathway-level
navigation here, subject to accuracy validation of inferred identifiers.

### Recon3D

Recon3D reaches 70.0% non-SBO general coverage but only 14.4% pathway coverage.
The tool is useful for identity lookup, reaction-type grouping, transport, and
cross-reference search across a very large model. It is not yet sufficient as a
complete human pathway browser. The difference suggests that adding more broad
types would improve the headline coverage without solving the real pathway gap.

### e_coli_core

The small core model reaches 95.8% non-SBO general coverage and 49.5% pathway
coverage. SemGEM is useful for central-metabolism exploration, but the model has
only 95 reactions, so its intervals are wide and it should not dominate
conclusions about large GEMs.

### iAM_Pf480

Non-SBO coverage is 64.5% and pathway coverage 29.7%, mainly from MetaNetX,
Rhea, and chemistry inference. SemGEM provides a useful initial index and
reduces manual inspection, but pathway organisation remains partial.

### iCN900

Pathway coverage is 37.2%, with strong agreement in provider reach between
MetaNetX and Rhea. SemGEM is moderately useful for pathway browsing and
candidate selection. The overlap between sources may also provide valuable
provenance for later confidence calibration.

### iEC1364_W

Despite 100% SBO coverage, non-SBO coverage is 47.1% and pathway coverage only
6.9%. This model exposes the same namespace/standardisation weakness as the
low-performing GCF models. SemGEM currently helps with broad types, but its
pathway output is not sufficiently informative for research use.

### iJN678

This is the best pathway result at 73.2%. However, its source subsystem labels
alone provide 68.1%; removing both SBO and source subsystems reduces pathway
coverage to 52.7%. SemGEM is highly useful on this model, while the ablation
shows that part of the success comes from compiling existing model knowledge
rather than reconstructing it independently.

### iJO1366

Pathway coverage is 57.4% and non-SBO general coverage 97.9%. Without original
subsystems and SBO, pathway coverage is 33.8%. SemGEM is highly useful for
unified browsing and application development, but roughly 24 percentage points
of pathway reach come from the model’s existing subsystem information.

### iML1515

This model has no usable subsystem labels in the catalogue. SemGEM still
provides 71.1% non-SBO general coverage and 29.5% pathway coverage, mostly
through MetaNetX, Rhea, and chemistry-based matching. This is a good example of
portable enrichment providing moderate value without relying on source
subsystems.

### iMM904

SemGEM reaches 93.1% non-SBO general coverage and 58.8% pathway coverage.
Source subsystems contribute strongly; portable pathway coverage is 36.1%.
The tool is highly useful for browsing and downstream application development,
but the portable enrichment result is the fairer measure of added value.

### iYO844

Pathway coverage is 36.1%, almost entirely from external/chemistry enrichment;
the model-only pathway coverage is only 3.0% despite source subsystem fields
being present. This indicates a terminology-normalisation gap: the labels are
not matching the current canonical concept system. SemGEM is moderately useful,
and synonym/canonical-label work could improve it without model-specific rules.

### iYS1720

With no source subsystem contribution, SemGEM obtains 68.6% non-SBO coverage
and 25.8% pathway coverage. KEGG, MetaNetX, and Rhea all contribute. It is useful
as a first semantic index and cross-reference layer, but three quarters of the
model still lack pathway allocation.

## Overall research usefulness

The evaluation supports SemGEM’s central premise: no single source or model
field provides consistent semantic organisation across the cohort. Some models
are rich in SBO but poor in pathways; some expose Rhea but not KEGG; some can be
interpreted from local identifiers; and others depend on metabolite chemistry.
A developer supporting all 19 models would otherwise need to implement these
cases separately.

SemGEM is currently useful for:

- normalising access to heterogeneous reaction identities and evidence;
- finding broad reaction classes across most models;
- obtaining partial pathway groupings without model-specific application code;
- showing evidence provenance and cross-provider support;
- identifying poorly annotated models and the exact source of their coverage
  gap;
- providing a single multi-model SQL catalogue for downstream tools.

It is not yet reliable as:

- a complete pathway reconstruction system;
- a substitute for biological curation;
- an accuracy-certified classifier for all organisms;
- a calibrated probabilistic system;
- a universal solution for models with opaque local identifiers and poorly
  standardised metabolites.

## Recommended next evaluation and development priorities

1. Preserve three separate headline metrics in all future reports:
   non-SBO general coverage, pathway coverage, and portable pathway coverage
   without source subsystems.
2. Build an independent, blinded reference set. Hold out at least one model
   family from rule development and manually curate a stratified reaction
   sample including negatives.
3. Report micro- and macro-averaged precision, recall, F1, and per-concept
   confusion matrices. The current coverage totals are micro-averaged and can
   be dominated by Recon3D.
4. Calibrate scores and thresholds on one set and evaluate them on another.
   Use precision–recall curves where concept prevalence is low.
5. Prioritise namespace and metabolite standardisation for
   `GCF_002079545_1_json`, `GCF_003053245_1_json`,
   `GCF_019456065_1`, and `iEC1364_W`.
6. Improve canonical pathway labels and synonyms, particularly where subsystem
   fields exist but contribute little, as in `iYO844`.
7. Measure cross-provider agreement and conflict, not only isolated provider
   reach. Agreement is potentially stronger evidence; disagreement should be
   retained as provenance rather than silently collapsed.
8. Keep static rules general and biologically motivated. Avoid rules created
   solely to improve one model’s benchmark.
9. Add macro-average model coverage, median model coverage, and bootstrap
   intervals to the thesis analysis so duplicate or very large models do not
   distort conclusions.

## Bottom line

The current system is already useful as a heterogeneous-model semantic indexing
layer, especially for models such as `MODEL1507180064`, `iJN678`, `iJO1366`,
and `iMM904`. Its main unresolved limitation is pathway completeness, not broad
reaction classification. The fairest current summary is:

- **68.2%** of reactions receive a non-SBO semantic conclusion;
- **28.6%** receive a pathway conclusion;
- **25.9%** receive a pathway conclusion without relying on either SBO or
  original subsystem labels;
- the available development accuracy benchmarks are promising
  (curated F1 0.855; iRC comparable-subsystem F1 0.751), but are not yet
  independent enough for a final thesis accuracy claim.
