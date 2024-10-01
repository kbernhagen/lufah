# SPDX-FileCopyrightText: 2024-present foldingathome.org
# SPDX-License-Identifier: MIT

"""Updatable from Web Control translated to python"""

__all__ = ["Updatable"]

import datetime
from typing import Any, Dict, List, Union


def _is_dict(o: Any) -> bool:
    """
    Checks if the given input is a non-null object (dictionary in Python).

    Args:
        o (Any): The input to check.

    Returns:
        bool: True if the input is a dictionary, otherwise False.
    """
    return o is not None and isinstance(o, dict)


class Updatable(dict):
    """
    A class that allows for initializing state from a dictionary and supports array updates.

    Methods:
        clean_key: Cleans a key by replacing hyphens with underscores (if key is a string).
        clean_keys: Recursively cleans keys of dictionaries or lists.
        do_update: Updates the object using a specific update format.
    """

    def __init__(self, data: dict = None, compat_mode=False, **kwargs) -> None:
        """
        Initializes the Updatable instance from a dict and/or kwargs.

        Args:
            data (Any): The initial JSON data dictionary.
            compat_mode (bool): Convert '-' to '_' in keys for 8.1 compatability.
                Do not use with 8.3+.
            kwargs: Additional keys and values to store.
        """
        self.compat_mode = compat_mode
        if not data:
            data = {}
        if self.compat_mode:
            self.update(self.clean_keys(data), **kwargs)
        else:
            self.update(data, **kwargs)
        self._last_update = datetime.datetime.now()

    @staticmethod
    def clean_key(key: Any) -> Any:
        """
        Cleans a given key by replacing hyphens with underscores if the key is a string.

        Args:
            key (Any): The key to clean.

        Returns:
            Any: The cleaned key if it's a string, or the original key if not.
        """
        if isinstance(key, str) and len(key) <= 16:
            return key.replace("-", "_")
        return key

    @staticmethod
    def clean_keys(data: Any) -> Any:
        """
        Recursively cleans the keys of a dictionary by replacing hyphens with underscores.

        Args:
            data (Any): A dictionary, list, or any other type of data.

        Returns:
            Any: The data with cleaned keys, or the original data if no cleaning is needed.
        """
        if isinstance(data, list):
            return [Updatable.clean_keys(value) for value in data]
        if _is_dict(data):
            return {
                Updatable.clean_key(key): Updatable.clean_keys(value)
                for key, value in data.items()
            }
        return data

    @property
    def last_update(self) -> datetime:
        """Return timestamp of last list update."""
        return self._last_update

    def do_update(self, update: List[Union[str, int, Any]]) -> None:  # pylint: disable=R0912
        """
        Updates the object using a list containing a key path and value.

        The update is a list where elements indicate keys or indices to traverse,
        with the final element being the value to update. If the value is `None`, the
        corresponding attribute item is deleted.

        Index -1 means append value to list.
        Last key index -2 means extend list with items in value list.
        Index one beyond max index also means append value to list.
        Only the last key can be -2.

        Args:
            update (List[Union[str, int, Any]]): A JSON list describing the update operation.
        """
        if not isinstance(update, list):
            return
        self._last_update = datetime.datetime.now()

        obj: Union[Updatable, Dict, List] = self
        i = 0

        while i < len(update) - 2:
            # Traverse key path prior to last key, creating missing implied lists and dicts
            if self.compat_mode:
                key = self.clean_key(update[i])
            else:
                key = update[i]
            i += 1
            next_key_is_int = isinstance(update[i], int)

            # If value is missing, create empty list or dict based on type of next key
            # Handle index -1 before last key, even though web control does not
            if isinstance(obj, dict) and key not in obj:
                if next_key_is_int:
                    obj[key] = []
                else:
                    obj[key] = {}
            elif isinstance(obj, list) and (key == -1 or key == len(obj)):
                key = len(obj)
                if next_key_is_int:
                    obj.append([])  # pylint: disable=no-member
                else:
                    obj.append({})  # pylint: disable=no-member

            obj = obj[key]

        is_array = isinstance(obj, list)
        if self.compat_mode:
            key = self.clean_key(update[i])  # last key
        else:
            key = update[i]  # last key
        i += 1
        value = update[i]  # last element is value
        if self.compat_mode and value is not None:
            value = Updatable.clean_keys(value)  # Note: web control does not do this

        if is_array and key == -1:
            obj.append(value)
        elif is_array and key == -2:
            obj.extend(value)
        elif is_array and key >= len(obj):
            # key > len should probably be logged as warning/error
            obj.append(value)
        elif is_array and value is None:
            obj.pop(key)
        elif value is None:
            del obj[key]
        else:
            obj[key] = value
