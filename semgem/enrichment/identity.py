import re

from semgem.core.records import AnnotationInputRecord


_KEGG_REACTION_ID = re.compile(r"^(R\d{5})(?:_[A-Za-z][A-Za-z0-9]*)?$")
_RHEA_REACTION_ID = re.compile(
    r"^(?:RHEA[:_])?(\d+)(?:_[A-Za-z][A-Za-z0-9]*)?$",
    re.IGNORECASE,
)
_METANETX_REACTION_ID = re.compile(
    r"^(MNXR\d+)(?:_[A-Za-z][A-Za-z0-9]*)?$",
    re.IGNORECASE,
)
_BIGG_REACTION_CANDIDATE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,127}$")
_BIGG_METABOLITE_CANDIDATE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_]{0,127}$")
_KEGG_COMPOUND_ID = re.compile(r"^(C\d{5})$", re.IGNORECASE)
_METANETX_CHEMICAL_ID = re.compile(r"^(MNXM\d+)$", re.IGNORECASE)


def infer_identity_inputs(
    database,
    annotations: list[AnnotationInputRecord] | None = None,
) -> list[AnnotationInputRecord]:
    """Infer strict external reaction accessions from local reaction IDs.

    These records are provider inputs, not source-model annotations. They
    therefore have no annotation row identifier and never alter the raw
    annotation table.
    """

    inputs = []
    existing = {
        (annotation.entity_id, annotation.source)
        for annotation in (annotations or [])
    }
    for entity in database.evidence_entity_rows():
        if entity["entity_type"] != "reaction":
            continue
        original_id = entity["original_id"]
        inferred = _infer_source_identifier(original_id)
        candidates = [inferred] if inferred is not None else []
        if inferred is None and _BIGG_REACTION_CANDIDATE.fullmatch(original_id):
            # This is only a provider lookup candidate. MetaNetX must confirm
            # the exact identifier before it becomes an assertion/evidence.
            candidates.append(("bigg.reaction", original_id))
        for source, identifier in candidates:
            if (entity["entity_id"], source) in existing:
                continue
            inputs.append(
                AnnotationInputRecord(
                    annotation_id=None,
                    entity_id=entity["entity_id"],
                    source=source,
                    identifier=identifier,
                )
            )
    for metabolite in database.metabolite_standardization_rows():
        entity_id = metabolite["entity_id"]
        identifier = metabolite["compartment_free_id"]
        candidates = []
        if match := _KEGG_COMPOUND_ID.fullmatch(identifier):
            candidates.append(("kegg.compound", match.group(1).upper()))
        elif match := _METANETX_CHEMICAL_ID.fullmatch(identifier):
            candidates.append(("metanetx.chemical", match.group(1).upper()))
        elif _BIGG_METABOLITE_CANDIDATE.fullmatch(identifier):
            candidates.append(("bigg.metabolite", identifier))
        for source, candidate_identifier in candidates:
            if (entity_id, source) in existing:
                continue
            inputs.append(
                AnnotationInputRecord(
                    annotation_id=None,
                    entity_id=entity_id,
                    source=source,
                    identifier=candidate_identifier,
                )
            )
    return inputs


def _infer_source_identifier(value: str) -> tuple[str, str] | None:
    kegg = _KEGG_REACTION_ID.fullmatch(value)
    if kegg:
        return "kegg.reaction", kegg.group(1)
    metanetx = _METANETX_REACTION_ID.fullmatch(value)
    if metanetx:
        return "metanetx.reaction", metanetx.group(1).upper()
    rhea = _RHEA_REACTION_ID.fullmatch(value)
    if rhea and value.upper().startswith("RHEA"):
        return "rhea", rhea.group(1)
    return None
