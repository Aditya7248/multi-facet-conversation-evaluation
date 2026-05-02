"""Unit tests for text normalisation primitives — fast, no I/O."""

from __future__ import annotations

import pytest

from src.utils.text import normalize_facet_name, slugify, split_camel


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Risktaking", "Risktaking"),
        ("Democratic Leadership:", "Democratic Leadership"),
        ("HonestyHumility:", "Honesty Humility"),
        ("793. Sufi practice: Dhikr repetitions / day", "Sufi practice: Dhikr repetitions / day"),
        ("  Compassion   Fatigue   ", "Compassion Fatigue"),
        ("FSH level", "FSH level"),
        ("camelCase", "Camel Case"),
        ("Numerical Reasoning Subcomponents:", "Numerical Reasoning Subcomponents"),
    ],
)
def test_normalize_facet_name(raw: str, expected: str) -> None:
    assert normalize_facet_name(raw) == expected


def test_slugify_basic() -> None:
    assert slugify("Compassion Fatigue") == "compassion-fatigue"
    assert slugify("Honesty-Humility") == "honesty-humility"
    assert slugify("FSH level") == "fsh-level"
    assert slugify("???") == "facet"


def test_split_camel() -> None:
    assert split_camel("HonestyHumility") == "Honesty Humility"
    assert split_camel("plainword") == "plainword"
    assert split_camel("ABCdef") == "ABCdef"
