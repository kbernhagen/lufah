"""Tests for lufah.util.munged_group_name"""

import pytest

from lufah.exceptions import FahClientGroupDoesNotExist
from lufah.util import munged_group_name

SNAPSHOT = {"groups": {"": {}, "a": {}, "/legacy": {}}}


def test_none_group():
    assert munged_group_name(None, SNAPSHOT) is None


def test_existing_groups():
    assert munged_group_name("", SNAPSHOT) == ""
    assert munged_group_name("a", SNAPSHOT) == "a"
    assert munged_group_name("/legacy", SNAPSHOT) == "/legacy"


def test_missing_group_has_no_hint():
    with pytest.raises(FahClientGroupDoesNotExist) as e:
        munged_group_name("nope", SNAPSHOT)
    assert "Did you mean" not in str(e.value)


def test_leading_slash_group_hint():
    """'legacy' does not exist but '/legacy' does: hint to use '//legacy'"""
    with pytest.raises(FahClientGroupDoesNotExist) as e:
        munged_group_name("legacy", SNAPSHOT)
    assert "Did you mean '//legacy'?" in str(e.value)
