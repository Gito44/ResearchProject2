import re
import unicodedata

from semgem.evidence.rules import ConceptDefinition


_SEPARATORS = re.compile(r"[/_\-&]+")
_PUNCTUATION = re.compile(r"[^\w\s]")
_WHITESPACE = re.compile(r"\s+")


def normalize_label(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).lower().strip()
    text = _SEPARATORS.sub(" ", text)
    text = _PUNCTUATION.sub("", text)
    return _WHITESPACE.sub(" ", text).strip()


class ConceptRegistry:
    def __init__(self, concepts: dict[str, ConceptDefinition]):
        self.concepts = concepts
        self._label_index: dict[str, set[str]] = {}
        self._compact_label_index: dict[str, set[str]] = {}
        for concept in concepts.values():
            for label in (concept.preferred_label, *concept.synonyms):
                normalized = normalize_label(label)
                if normalized:
                    self._label_index.setdefault(normalized, set()).add(
                        concept.concept_id
                    )
                    compact = normalized.replace(" ", "")
                    self._compact_label_index.setdefault(compact, set()).add(
                        concept.concept_id
                    )

    def match_label(self, label: str | None) -> tuple[str, ...]:
        if not label:
            return ()
        normalized = normalize_label(label)
        matches = self._label_index.get(normalized)
        if matches:
            return tuple(sorted(matches))

        # Some COBRA/BiGG SBML exports encode subsystem labels as identifiers,
        # for example S_Fatty_Acid__Biosynthesis or
        # S_GlycolysisGluconeogenesis. Apply compact matching only to this
        # explicit format so ordinary labels do not become fuzzy matches.
        if label.startswith("S_"):
            decoded = normalize_label(label[2:])
            matches = self._label_index.get(decoded)
            if not matches:
                matches = self._compact_label_index.get(decoded.replace(" ", ""))
            if matches:
                return tuple(sorted(matches))
        return ()
