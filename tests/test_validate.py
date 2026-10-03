"""Tests for lufah.validate"""

from lufah import validate as valid

H = ".example.com"


def test_address_multi_preserves_order_and_dedupes():
    """Multiple hosts keep the order given; duplicates are dropped"""
    assert valid.address(f"b{H}:1,a{H}:2,b{H}:1") == f"b{H}:1,a{H}:2"


def test_address_multi_order_is_stable():
    """Result must not vary between calls"""
    names = ["h5", "h3", "h9", "h1", "h7"]
    peer = ",".join(f"{n}{H}:1" for n in names + ["h3"])
    expected = ",".join(f"{n}{H}:1" for n in names)
    assert all(valid.address(peer) == expected for _ in range(20))


def test_address_multi_ignores_empty_items():
    """Empty items between commas are ignored"""
    assert valid.address(f"b{H}:1,,a{H}:2,") == f"b{H}:1,a{H}:2"
