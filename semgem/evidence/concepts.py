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

    def validate_hierarchy(self) -> None:
        """Reject cycles before hierarchy expansion can reach runtime."""
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(concept_id: str) -> None:
            if concept_id in visiting:
                raise ValueError(f"Concept hierarchy contains a cycle at '{concept_id}'.")
            if concept_id in visited:
                return
            visiting.add(concept_id)
            for parent_id in self.concepts[concept_id].parents:
                visit(parent_id)
            visiting.remove(concept_id)
            visited.add(concept_id)

        for concept_id in self.concepts:
            visit(concept_id)

    def ancestors(self, concept_id: str) -> tuple[str, ...]:
        """Return all broader concepts, nearest parents before distant ones."""
        if concept_id not in self.concepts:
            raise KeyError(concept_id)
        ordered: list[str] = []
        seen: set[str] = set()
        queue = list(self.concepts[concept_id].parents)
        while queue:
            parent_id = queue.pop(0)
            if parent_id in seen:
                continue
            seen.add(parent_id)
            ordered.append(parent_id)
            queue.extend(self.concepts[parent_id].parents)
        return tuple(ordered)

    def hierarchy_compatible(self, first: str, second: str) -> bool:
        """Return whether two concepts are equal or on one hierarchy branch."""
        return (
            first == second
            or first in self.ancestors(second)
            or second in self.ancestors(first)
        )

    def match_anchors(self, text: str | None) -> tuple[tuple[str, str], ...]:
        """Match explicit, curated semantic anchors at normalized word boundaries."""
        normalized_text = f" {normalize_label(text or '')} "
        matches = []
        for concept in self.concepts.values():
            for anchor in concept.anchors:
                normalized_anchor = normalize_label(anchor)
                if normalized_anchor and f" {normalized_anchor} " in normalized_text:
                    matches.append((concept.concept_id, anchor))
                    break
            else:
                for fragment in concept.anchor_fragments:
                    normalized_fragment = normalize_label(fragment)
                    if normalized_fragment and normalized_fragment in normalized_text:
                        matches.append((concept.concept_id, fragment))
                        break
        return tuple(sorted(matches))
