from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

from semgem.core.records import (
    AnnotationInputRecord,
    EnrichmentAssertionRecord,
    EnrichmentResult,
    EntityAssertionEvidenceRecord,
    ExternalTermRecord,
    ExternalTermRelationshipRecord,
    ProviderRelationshipEvidenceRecord,
)
from semgem.enrichment.base import EnrichmentProvider
from semgem.enrichment.metanetx import MetaNetXProvider


_MNX_TERM = re.compile(r"^(\S+)\s+(MNXM[A-Za-z0-9]+)@(?:MNXC|MNXD)\S+$")


class MetaNetXChemistryProvider(EnrichmentProvider):
    """Standardize metabolites and match fully mapped reaction chemistry."""

    name = "metanetx_chemistry"
    annotation_sources = frozenset(
        {
            "bigg.metabolite",
            "kegg.compound",
            "metanetx.chemical",
            "chebi",
        }
    )

    def __init__(
        self,
        chem_xref_path: str | Path,
        reac_prop_path: str | Path,
        reac_xref_path: str | Path,
        chem_prop_path: str | Path | None = None,
    ):
        self.chem_xref_path = Path(chem_xref_path)
        self.reac_prop_path = Path(reac_prop_path)
        self.reac_xref_path = Path(reac_xref_path)
        self.chem_prop_path = (
            Path(chem_prop_path) if chem_prop_path is not None else None
        )
        for path in (
            self.chem_xref_path,
            self.reac_prop_path,
            self.reac_xref_path,
        ):
            if not path.is_file():
                raise FileNotFoundError(f"MNXref file not found: {path}")
        if self.chem_prop_path is not None and not self.chem_prop_path.is_file():
            raise FileNotFoundError(
                f"MNXref chemical property file not found: {self.chem_prop_path}"
            )
        self.resource_version = self._resource_version(self.chem_xref_path)
        self.database = None

    def use_catalog_cache(self, database) -> None:
        self.database = database

    def enrich(
        self,
        annotations: Iterable[AnnotationInputRecord],
        run_id: int,
    ) -> EnrichmentResult:
        relevant = tuple(
            annotation
            for annotation in annotations
            if annotation.source in self.annotation_sources
        )
        by_key: dict[str, list[AnnotationInputRecord]] = defaultdict(list)
        for annotation in relevant:
            key = self._xref_key(annotation.source, annotation.identifier)
            if key is not None:
                by_key[key].append(annotation)

        matches: dict[str, set[str]] = defaultdict(set)
        for key, mnx_id, _ in self._xref_rows(self.chem_xref_path):
            if key in by_key:
                matches[key].add(mnx_id)

        # Ambiguous cross-references are deliberately left unresolved.
        unique_matches = {
            key: next(iter(mnx_ids))
            for key, mnx_ids in matches.items()
            if len(mnx_ids) == 1
        }
        entity_candidates: dict[int, set[str]] = defaultdict(set)
        for key, annotations_for_key in by_key.items():
            mnx_id = unique_matches.get(key)
            if mnx_id is None:
                continue
            for annotation in annotations_for_key:
                entity_candidates[annotation.entity_id].add(mnx_id)
        # Cross-source disagreement is ambiguity, not permission to let the
        # last candidate silently win.
        metabolite_mnx = {
            entity_id: next(iter(mnx_ids))
            for entity_id, mnx_ids in entity_candidates.items()
            if len(mnx_ids) == 1
        }
        matched_mnx = set(metabolite_mnx.values())
        names = self._chemical_names(matched_mnx)

        terms: dict[tuple[str, str], ExternalTermRecord] = {}
        assertions = []
        relationships = []
        now = datetime.now(timezone.utc).isoformat()

        for mnx_id in sorted(matched_mnx):
            terms[("metanetx.chemical", mnx_id)] = ExternalTermRecord(
                source="metanetx.chemical",
                identifier=mnx_id,
                term_type="metabolite",
                name=names.get(mnx_id),
                source_version=self.resource_version,
            )
        for key, annotations_for_key in sorted(by_key.items()):
            mnx_id = unique_matches.get(key)
            if mnx_id is None:
                continue
            for annotation in annotations_for_key:
                if metabolite_mnx.get(annotation.entity_id) != mnx_id:
                    continue
                assertions.append(
                    EnrichmentAssertionRecord(
                        entity_id=annotation.entity_id,
                        predicate="maps_to_mnxref_chemical",
                        term_source="metanetx.chemical",
                        term_identifier=mnx_id,
                        evidence=(
                            EntityAssertionEvidenceRecord(
                                provider=self.name,
                                evidence_type=(
                                    "source_model_annotation"
                                    if annotation.annotation_id is not None
                                    else "model_identifier_pattern"
                                ),
                                retrieval_method="mnxref_chem_xref",
                                run_id=run_id,
                                source_annotation_id=annotation.annotation_id,
                                source_identifier=annotation.identifier,
                                resource_version=self.resource_version,
                                retrieved_at=now,
                            ),
                        ),
                    )
                )

        reaction_matches = self._match_reaction_signatures(metabolite_mnx)
        matched_reactions = set(reaction_matches.values())
        reaction_crossrefs: dict[str, set[tuple[str, str]]] = {
            mnx_id: set() for mnx_id in matched_reactions
        }
        for key, mnx_id, _ in self._xref_rows(self.reac_xref_path):
            if mnx_id not in matched_reactions:
                continue
            source, identifier = MetaNetXProvider._split_xref(key)
            if source in MetaNetXProvider._exported_sources:
                reaction_crossrefs[mnx_id].add((source, identifier))

        for mnx_id in sorted(matched_reactions):
            terms[("metanetx.reaction", mnx_id)] = ExternalTermRecord(
                source="metanetx.reaction",
                identifier=mnx_id,
                term_type="reaction",
                source_version=self.resource_version,
            )
            for source, identifier in sorted(reaction_crossrefs[mnx_id]):
                terms[(source, identifier)] = ExternalTermRecord(
                    source=source,
                    identifier=identifier,
                    term_type="reaction",
                    source_version=self.resource_version,
                )
                relationships.append(
                    ExternalTermRelationshipRecord(
                        subject_source="metanetx.reaction",
                        subject_identifier=mnx_id,
                        predicate="cross_references",
                        object_source=source,
                        object_identifier=identifier,
                        evidence=(
                            ProviderRelationshipEvidenceRecord(
                                provider=self.name,
                                retrieval_method="mnxref_reac_xref",
                                run_id=run_id,
                                source_identifier=mnx_id,
                                resource_version=self.resource_version,
                                retrieved_at=now,
                            ),
                        ),
                    )
                )

        for entity_id, mnx_id in sorted(reaction_matches.items()):
            assertions.append(
                EnrichmentAssertionRecord(
                    entity_id=entity_id,
                    predicate="matches_mnxref_reaction_signature",
                    term_source="metanetx.reaction",
                    term_identifier=mnx_id,
                    evidence=(
                        EntityAssertionEvidenceRecord(
                            provider=self.name,
                            evidence_type="stoichiometric_signature_match",
                            retrieval_method="mnxref_reac_prop",
                            run_id=run_id,
                            source_identifier=mnx_id,
                            resource_version=self.resource_version,
                            retrieved_at=now,
                        ),
                    ),
                )
            )

        requested = set(by_key)
        resolved = set(unique_matches)
        return EnrichmentResult(
            provider=self.name,
            resource_version=self.resource_version,
            terms=tuple(terms[key] for key in sorted(terms)),
            relationships=tuple(relationships),
            assertions=tuple(assertions),
            requested_identifiers=tuple(sorted(requested)),
            resolved_identifiers=tuple(sorted(resolved)),
            unresolved_identifiers=tuple(sorted(requested - resolved)),
            warnings=(),
        )

    def _match_reaction_signatures(
        self,
        metabolite_mnx: dict[int, str],
    ) -> dict[int, str]:
        if self.database is None:
            return {}
        grouped: dict[int, list[dict]] = defaultdict(list)
        for row in self.database.reaction_stoichiometry_rows():
            grouped[row["reaction_entity_id"]].append(row)

        wanted: dict[tuple, list[int]] = defaultdict(list)
        for reaction_entity_id, rows in grouped.items():
            if not rows or any(
                row["metabolite_entity_id"] not in metabolite_mnx
                for row in rows
            ):
                continue
            # Compartmental transport already has a stronger structural rule.
            if len({row["compartment"] for row in rows}) > 1:
                continue
            left = defaultdict(Decimal)
            right = defaultdict(Decimal)
            for row in rows:
                target = left if row["coefficient"] < 0 else right
                target[metabolite_mnx[row["metabolite_entity_id"]]] += Decimal(
                    str(abs(row["coefficient"]))
                )
            signature = self._signature(left, right)
            if signature is not None:
                wanted[signature].append(reaction_entity_id)

        reference: dict[tuple, set[str]] = defaultdict(set)
        with self.reac_prop_path.open(encoding="utf-8") as file:
            for line in file:
                if not line or line.startswith("#"):
                    continue
                fields = line.rstrip("\n").split("\t")
                if len(fields) < 2:
                    continue
                signature = self._parse_mnx_equation(fields[1])
                if signature in wanted:
                    reference[signature].add(fields[0])

        return {
            entity_id: next(iter(reference[signature]))
            for signature, entity_ids in wanted.items()
            if len(reference.get(signature, ())) == 1
            for entity_id in entity_ids
        }

    @classmethod
    def _parse_mnx_equation(cls, equation: str) -> tuple | None:
        if " = " not in equation:
            return None
        left_text, right_text = equation.split(" = ", 1)

        def parse_side(value: str):
            side = defaultdict(Decimal)
            if not value.strip():
                return side
            for term in value.split(" + "):
                match = _MNX_TERM.fullmatch(term.strip())
                if match is None:
                    return None
                try:
                    coefficient = Decimal(match.group(1))
                except InvalidOperation:
                    return None
                side[match.group(2)] += coefficient
            return side

        left = parse_side(left_text)
        right = parse_side(right_text)
        if left is None or right is None:
            return None
        return cls._signature(left, right)

    @staticmethod
    def _signature(left: dict, right: dict) -> tuple | None:
        if not left or not right:
            return None

        def side_signature(side):
            return tuple(
                sorted(
                    (identifier, str(coefficient.normalize()))
                    for identifier, coefficient in side.items()
                    if coefficient
                )
            )

        forward = (side_signature(left), side_signature(right))
        reverse = (forward[1], forward[0])
        return min(forward, reverse)

    def _chemical_names(self, identifiers: set[str]) -> dict[str, str]:
        if self.chem_prop_path is None or not identifiers:
            return {}
        names = {}
        with self.chem_prop_path.open(encoding="utf-8") as file:
            for line in file:
                if not line or line.startswith("#"):
                    continue
                fields = line.rstrip("\n").split("\t", 2)
                if len(fields) >= 2 and fields[0] in identifiers:
                    names[fields[0]] = fields[1]
        return names

    @classmethod
    def _xref_rows(cls, path: Path):
        with path.open(encoding="utf-8") as file:
            for line in file:
                if not line or line.startswith("#"):
                    continue
                fields = line.rstrip("\n").split("\t", 2)
                if len(fields) < 2:
                    continue
                if path.name == "chem_xref.tsv":
                    key = cls._normalize_chemical_xref(fields[0])
                else:
                    key = MetaNetXProvider._normalize_file_xref(fields[0])
                if key is not None:
                    yield key, fields[1], fields[2] if len(fields) > 2 else ""

    @staticmethod
    def _normalize_chemical_xref(value: str) -> str | None:
        source, separator, identifier = value.partition(":")
        if not separator:
            if value.startswith("MNXM"):
                return f"metanetx.chemical:{value}"
            return None
        aliases = {
            "biggM": "bigg.metabolite",
            "bigg.metabolite": "bigg.metabolite",
            "keggC": "kegg.compound",
            "kegg.compound": "kegg.compound",
            "chebi": "chebi",
            "mnx": "metanetx.chemical",
            "metanetx.chemical": "metanetx.chemical",
        }
        normalized_source = aliases.get(source)
        if normalized_source is None:
            return None
        if normalized_source == "bigg.metabolite":
            identifier = identifier.removeprefix("M_")
        if normalized_source == "kegg.compound":
            identifier = identifier.removeprefix("M_").upper()
        if normalized_source == "metanetx.chemical":
            identifier = identifier.upper().removeprefix("MNX:")
        return f"{normalized_source}:{identifier}"

    @classmethod
    def _xref_key(cls, source: str, identifier: str) -> str | None:
        if source not in cls.annotation_sources:
            return None
        value = identifier.strip()
        if source == "kegg.compound":
            value = value.removeprefix("cpd:").upper()
        elif source == "metanetx.chemical":
            value = value.upper().removeprefix("MNX:")
        elif source == "chebi":
            value = value.upper().removeprefix("CHEBI:")
        return f"{source}:{value}"

    @staticmethod
    def _resource_version(path: Path) -> str:
        with path.open(encoding="utf-8") as file:
            for line in file:
                if line.startswith("#VERSION:"):
                    return f"MNXref {line.split(':', 1)[1].strip()}"
                if not line.startswith("#"):
                    break
        return "MNXref"
