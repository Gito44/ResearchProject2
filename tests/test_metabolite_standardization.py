import pytest

from semgem.standardize.metabolites import (
    normalize_metabolite_name,
    strip_compartment_suffix,
)


@pytest.mark.parametrize(
    ("metabolite_id", "compartment", "expected"),
    [
        ("glc__D_c", "c", "glc__D"),
        ("glc__D[c]", "c", "glc__D"),
        ("glc__D__c", "c", "glc__D"),
        ("C00031", "c", "C00031"),
        ("atp_c", None, "atp_c"),
    ],
)
def test_strip_compartment_suffix_is_conservative(
    metabolite_id,
    compartment,
    expected,
):
    assert strip_compartment_suffix(metabolite_id, compartment) == expected


def test_normalize_metabolite_name_preserves_chemical_signs():
    assert normalize_metabolite_name("  L-Glutamate + H⁺  ") == (
        "l-glutamate + h+"
    )
