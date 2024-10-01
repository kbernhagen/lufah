"""pytest updatable"""

import json

import pytest  # noqa: F401

from lufah.updatable import Updatable
from lufah.util import load_json_objects_from_file

# Test data for initializing Updatable and testing clean_keys
sample_data = {
    "name": "example",
    "nested-data": {"value": 42, "inner-data": {"key-name": "test"}},
    "list-data": [{"item-name": "first"}, {"item-name": "second"}],
}

# Test data for updating
update_data = [
    ["nested-data", "inner-data", "key-name", "updated"],
    ["list-data", 0, "item-name", "updated-first"],
    ["list-data", -1, {"item_name": "third"}],
    ["nested-data", "value", None],  # Remove 'value' from 'nested-data'
    ["list-data", 1, None],  # Remove the second item in 'list-data'
    ["list-data", 2, {"item-name": "fourth"}],  # index beyond bounds is an append
]


def test_kwargs():
    """Test that Updatable can be initialized via kwargs."""
    updatable = Updatable(a=1, b=2, c=3)
    assert updatable["b"] == 2


def test_clean_keys():
    """Test that the clean_keys method properly replaces hyphens with underscores."""
    updatable = Updatable(sample_data, compat_mode=True)
    assert updatable["nested_data"]["inner_data"]["key_name"] == "test"
    assert updatable["list_data"][0]["item_name"] == "first"
    assert updatable["list_data"][1]["item_name"] == "second"


def test_do_update():
    """Test the do_update method for applying updates to the object."""
    updatable = Updatable(sample_data, compat_mode=True)

    # Update an existing key's value
    updatable.do_update(update_data[0])
    assert updatable["nested_data"]["inner_data"]["key_name"] == "updated"

    # Update a value in a list element
    updatable.do_update(update_data[1])
    assert updatable["list_data"][0]["item_name"] == "updated-first"

    # Append a new element to a list
    updatable.do_update(update_data[2])
    assert updatable["list_data"][2]["item_name"] == "third"

    # Remove a key from a dictionary
    updatable.do_update(update_data[3])
    assert "value" not in updatable["nested_data"]

    # Remove an element from a list
    updatable.do_update(update_data[4])
    assert len(updatable["list_data"]) == 2

    # Append element for index beyond bounds
    updatable.do_update(update_data[5])
    assert len(updatable["list_data"]) == 3
    assert updatable["list_data"][2]["item_name"] == "fourth"

    # Non-list updates should be ignored
    updatable.do_update("ping")
    assert "p" not in updatable
    updatable.do_update({"zzz": 3})
    assert "zzz" not in updatable


def test_clean_key():
    """Test that the clean_key method replaces hyphens in string keys."""
    assert Updatable.clean_key("key-name") == "key_name"
    assert Updatable.clean_key("short-key") == "short_key"
    assert (
        Updatable.clean_key("this-key-is-too-long") == "this-key-is-too-long"
    )  # No change
    assert Updatable.clean_key(123) == 123  # Non-string keys remain unchanged


def test_initialization():
    """Test initialization of Updatable with nested dictionaries and lists."""
    updatable = Updatable(sample_data, compat_mode=True)
    assert updatable["name"] == "example"
    assert isinstance(updatable["nested_data"], dict)
    assert updatable["nested_data"]["inner_data"]["key_name"] == "test"
    assert isinstance(updatable["list_data"], list)
    assert len(updatable["list_data"]) == 2


def test_update_append_to_list():
    """Test appending to a list within the object."""
    updatable = Updatable({"list-data": [1, 2, 3]}, compat_mode=True)
    updatable.do_update(["list-data", -1, 4])
    assert updatable["list_data"] == [1, 2, 3, 4]
    updatable.do_update(["list-data", 222, 5])
    assert updatable["list_data"] == [1, 2, 3, 4, 5]


def test_update_remove_from_list():
    """Test removing an item from a list within the object."""
    updatable = Updatable({"list-data": [1, 2, 3]}, compat_mode=True)
    updatable.do_update(["list-data", 1, None])  # Remove the second element
    assert updatable["list_data"] == [1, 3]


def test_update_replace_value():
    """Test replacing a value in the object."""
    updatable = Updatable({"key": "value"}, compat_mode=True)
    updatable.do_update(["key", "new-value"])
    assert updatable["key"] == "new-value"


def test_real_data_with_final_state():
    """test with real data"""
    objects = load_json_objects_from_file("data/lufahwatch3.jsonl")
    state = Updatable(objects[0])
    for update in objects[1:]:
        state.do_update(update)
    with open("data/lufahwatch3final.json", encoding="utf-8") as f:
        final = json.load(f)
    assert state == final
