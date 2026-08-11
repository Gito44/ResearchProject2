import re
import unicodedata


_WHITESPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^a-z0-9+\-]+")


def strip_compartment_suffix(
    metabolite_id: str,
    compartment: str | None,
) -> str:
    """Remove a model compartment suffix without guessing other ID syntax."""
    value = str(metabolite_id or "")
    compartment = str(compartment or "")
    if not compartment:
        return value
    for suffix in (
        f"[{compartment}]",
        f"__{compartment}",
        f"_{compartment}",
    ):
        if value.endswith(suffix):
            return value[: -len(suffix)]
    return value


def normalize_metabolite_name(name: str | None) -> str:
    """Return a stable comparison label while preserving chemical signs."""
    value = unicodedata.normalize("NFKC", str(name or "")).lower().strip()
    value = _PUNCTUATION.sub(" ", value)
    return _WHITESPACE.sub(" ", value).strip()
