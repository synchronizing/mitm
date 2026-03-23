"""Type-agnostic item and dictionary collections."""

from __future__ import annotations

from typing import Any, Iterator, Optional, Union

ENCODE = "ascii"
ItemType = Union[bytes, str, int, bool, None, "Item"]


class Item:
    __slots__ = ["_item", "_type"]

    def __init__(self, item: ItemType):
        """
        An interface for type-agnostic operations between ``bytes``, ``str``, ``int``,
         ``bool``, and ``None``.

        Internally, the passed ``item`` object is stored as its ``bytes``
        representation. Any operation or modification to the new ``Item`` instance is
        done to the internal ``bytes`` object. The true usefulness of this container is
        for type-agnostic operations such as equality checks.

        Args:
            item: Input to be stored.

        Example:

            .. code-block:: python

                from toolbox.collections.item import Item

                item = Item("hello world")
                if b" world" in item:
                    item -= " world"

                print(item.raw, item.string)
                # >>> b'hello' hello

                print(repr(item))
                # >>> Item(bytes=b'hello', str='hello', int=None, bool=True, original_type=str)
        """
        self._type = type(item)
        self._item = self.byte_item(item=item)

    @property
    def raw(self) -> bytes:
        """
        Bytes representation of the passed item.
        """
        return self._item

    @property
    def string(self) -> str:
        """
        String representation of the passed item.
        """
        return self._item.decode(ENCODE)

    @property
    def integer(self) -> Union[int, None]:
        """
        Integer representation of the passed item.

        If passed item is not a sub class of type int or str.isdigit() this property
        returns None.
        """
        if issubclass(self._type, int) or self.string.isdigit():
            return int(self._item)
        else:
            return None

    @property
    def boolean(self) -> bool:
        """
        Boolean representation of the passed item.
        """
        if issubclass(self._type, int):
            return bool(int(self._item))
        else:
            return bool(self._item)

    @property
    def original(self) -> ItemType:
        """
        Original representation of the passed item.
        """
        if self._type is str and isinstance(self._item, bytes):
            return self._item.decode(ENCODE)
        elif self._type is type(None):
            return None

        return self._type(self._item)

    def replace(self, old: ItemType, new: ItemType, count: int = -1) -> bytes:
        """
        ``bytes.replace()`` functionality on item.

        See Python `docs <https://docs.python.org/3/library/stdtypes.html?highlight=replace#bytes.replace>`_ for more info.
        """
        old = self.byte_item(item=old)
        new = self.byte_item(item=new)
        return self.raw.replace(old, new, count)

    def __pos__(self):
        """
        Returns the string representation of the object.

        Example:

            .. code-block:: python

                from toolbox.collections.item import Item

                item = Item(100)
                print(+item, type(+item)) # >>> 100 <class 'str'>
        """
        return self.string

    def __neg__(self):
        """
        Returns the integer representation of the object.

        Example:

            .. code-block:: python

                from toolbox.collections.item import Item

                item = Item(100)
                print(-item, type(-item)) # >>> 100 <class 'int'>
        """
        return self.integer

    def __contains__(self, item: ItemType) -> bool:
        _item = self.byte_item(item=item)
        return _item in self._item

    def __eq__(self, item: ItemType) -> bool:
        _item = self.byte_item(item=item)
        return self._item == _item

    def __add__(self, item: ItemType) -> "Item":
        _item = self.byte_item(item=item)
        return Item(self._item + _item)

    def __iadd__(self, item: ItemType) -> "Item":
        self._item = (self + Item(item))._item
        return self

    def __sub__(self, item: ItemType) -> "Item":
        _item = self.byte_item(item=item)
        return Item(self._item.replace(_item, b""))

    def __isub__(self, item: ItemType) -> "Item":
        self._item = (self - Item(item))._item
        return self

    def __iter__(self) -> Iterator[str]:
        return iter(self.string)

    def __hash__(self) -> int:
        return hash(self._item)

    def __len__(self) -> int:
        return len(self.raw)

    def __bool__(self) -> bool:
        return self.boolean

    def __str__(self) -> str:
        return self.string

    def __repr__(self) -> str:
        return str(self.original)

    @staticmethod
    def byte_item(item: ItemType) -> "Item":
        """
        Converts passed item into its bytes representation, and returns an Item instance.

        Args:
            item: Item of str, bytes, int, bool, None, or Item to convert to an Item.
        """

        if isinstance(item, str):
            _item = item.encode(ENCODE)
        elif isinstance(item, bytes):
            _item = item
        elif isinstance(item, int):
            _item = b"%d" % item
        elif item is None:
            _item = b""
        elif isinstance(item, Item):
            _item = item.raw
        else:
            err = "Passed 'item' is not of type str, bytes, int, None, or Item."
            raise TypeError(err)

        return _item


class BaseDict(dict):
    """Dictionary with pretty :py:func:`__repr__` output.

    Base class that all other dictionaries in this file inherit from. :py:func:`__repr__` is
    replaced with ``<{class_name} {dictionary data}>`` output style for implicit inferences.

    Example:

        .. code-block:: python

            from toolbox.collections.mapping import BaseDict

            class NewDict(BaseDict):
                '''New dictionary example.'''

            d = NewDict({"hello": "world"})
            print(d) # >>> <NewDict {'hello': 'world'}>
    """

    def __repr__(self):
        return "<{} {}>".format(
            self.__class__.__name__,
            super(BaseDict, self).__repr__(),
        )


class ObjectDict(BaseDict):
    """Dictionary that can be accessed and set as though it was an object.

    Example:

        .. code-block:: python

            from toolbox.collections.mapping import ObjectDict

            d = ObjectDict({"hello": "world"})
            print(d) # >>> <ObjectDict {'hello': 'world'}>

            print(d.hello) # >>> 'world'

            d.hello = "mundo"
            print(d.hello) # >>> 'mundo'
    """

    def __getattr__(self, key: Any) -> Any:
        return self.__getitem__(key)

    def __setattr__(self, key: str, value: Any):
        return self.__setitem__(key, value)


class OverloadedDict(BaseDict):
    """Dictionary that can be added or subtracted.

    Example:

        .. code-block:: python

            from toolbox.collections.mapping import OverloadedDict

            d1 = OverloadedDict({"hello": "world"})
            d2 = {"ola": "mundo"}

            d1 += d2
            print(d1) # >>> <OverloadedDict {'hello': 'world', 'ola': 'mundo'}>

            d1 -= d2
            print(d1) # >>> <OverloadedDict {'hello': 'world'}>
    """

    def __add__(self, other: dict) -> dict:
        dct = {**self, **other}
        return OverloadedDict(dct)

    def __iadd__(self, other: dict) -> dict:
        self = self.__add__(other)
        return self

    def __sub__(self, other: dict) -> dict:
        dct = {k: v for k, v in self.items() if (k, v) not in other.items()}
        return OverloadedDict(dct)

    def __isub__(self, other: dict) -> dict:
        self = self.__sub__(other)
        return self


class UnderscoreAccessDict(BaseDict):
    """Dictionary that doesn't distinct keys with empty spaces and underscores.

    Example:

        .. code-block:: python

            from toolbox.collections.mapping import UnderscoreAccessDict

            d = UnderscoreAccessDict({"hello world": "ola mundo"})
            print(d) # >>> <UnderscoreAccessDict {'hello world': 'ola mundo'}>

            print(d['hello_world']) # >>> 'ola mundo'
    """

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, bytes):
            utw = key.replace(b"_", b" ")
            wtu = key.replace(b"_", b"")
        else:
            utw = key.replace("_", " ")
            wtu = key.replace("_", "")

        if utw in self:
            return super(UnderscoreAccessDict, self).__getitem__(utw)
        elif wtu in self:
            return super(UnderscoreAccessDict, self).__getitem__(wtu)

        return super(UnderscoreAccessDict, self).__getitem__(key)


class MultiEntryDict(BaseDict):
    """Dictionary that can have multiple entries for the same key.

    .. code-block:: python

        from toolbox.collections.mapping import MultiEntryDict

        d = MultiEntryDict({"hello": "world", "hello": "mundo"})
        print(d) # >>> <MultiEntryDict {'hello': ['world', 'mundo']}>

        d['hello'] = 'globo'
        print(d) # >>> <MultiEntryDict {'hello': ['world', 'mundo', 'globo']}>
    """

    def __setitem__(self, key, value):
        if key in self:
            if isinstance(self[key], list):
                self[key].append(value)
            else:
                super().__setitem__(key, [self[key], value])
        else:
            super(MultiEntryDict, self).__setitem__(key, value)


class ItemDict(BaseDict):
    """Dictionary composed of :py:class:`toolbox.collections.item.Item` key and values.

    Example:

        .. code-block:: python

            from toolbox.collections.mapping import ItemDict

            d = ItemDict({"100": "one hundred"})
            print(d)
            # >>> <ItemDict {100: one hundred}>

            print(d["100"] == d[100] == d[b"100"]) # >>> True
    """

    def __init__(self, dictionary: Optional[dict] = None, **kwargs):
        dictionary = dictionary or {}
        kwargs = kwargs or {}
        dictionary = {**dictionary, **kwargs}

        new = {}
        for k, v in dictionary.items():
            if isinstance(v, list):
                new[Item(k)] = [Item(i) for i in v]
            else:
                new[Item(k)] = Item(v)

        return super(ItemDict, self).__init__(new)

    def __getitem__(self, key: ItemType):
        return super(ItemDict, self).__getitem__(Item(key))

    def __setitem__(self, key: ItemType, value: ItemType):
        if isinstance(value, list):
            super(ItemDict, self).__setitem__(Item(key), [Item(i) for i in value])
        else:
            super(ItemDict, self).__setitem__(Item(key), Item(value))

    def __delitem__(self, key: ItemType):
        super(ItemDict, self).__delitem__(Item(key))

    def __contains__(self, key: ItemType):
        return super(ItemDict, self).__contains__(Item(key))

    def update(self, dictionary: Optional[dict] = None, **kwargs):
        dictionary = dictionary or {}
        super(ItemDict, self).update(
            {
                **{Item(k): Item(v) for k, v in dictionary.items()},
                **{Item(k): Item(v) for k, v in kwargs.items()},
            },
        )
