import pytest

from mitm.utils.http.item import (
    Item,
    ItemDict,
    MultiEntryDict,
    ObjectDict,
    OverloadedDict,
    UnderscoreAccessDict,
)


class Test_Item:
    def test_from_string(self):
        item = Item("hello")
        assert item.string == "hello"
        assert item.raw == b"hello"

    def test_from_bytes(self):
        item = Item(b"world")
        assert item.raw == b"world"
        assert item.string == "world"

    def test_from_int(self):
        item = Item(42)
        assert item.integer == 42
        assert item.string == "42"

    def test_from_bool_true(self):
        item = Item(True)
        assert item.boolean is True
        assert item.integer == 1

    def test_from_none(self):
        item = Item(None)
        assert item.raw == b""
        assert item.string == ""

    def test_falsy_int_zero(self):
        item = Item(0)
        assert item.integer == 0
        assert item.boolean is False
        assert bool(item) is False

    def test_from_item(self):
        inner = Item("hello")
        outer = Item(inner)
        assert outer.raw == inner.raw
        assert outer.string == "hello"

    def test_byte_item_unsupported_raises(self):
        with pytest.raises(TypeError):
            Item.byte_item(["not", "supported"])

    def test_pos_returns_string(self):
        item = Item(100)
        assert +item == "100"
        assert isinstance(+item, str)

    def test_neg_returns_int(self):
        item = Item(42)
        assert -item == 42
        assert isinstance(-item, int)

    def test_add(self):
        a = Item("hello")
        b = Item(" world")
        result = a + b
        assert result.string == "hello world"

    def test_sub_removes_substring(self):
        item = Item("hello world")
        result = item - " world"
        assert result.string == "hello"

    def test_isub(self):
        item = Item("hello world")
        item -= " world"
        assert item.string == "hello"

    def test_contains(self):
        item = Item("hello world")
        assert "hello" in item
        assert b"world" in item
        assert "xyz" not in item

    def test_eq(self):
        assert Item("hello") == "hello"
        assert Item("hello") == b"hello"
        assert Item(42) == 42

    def test_len(self):
        item = Item("hello")
        assert len(item) == 5

    def test_iter(self):
        item = Item("abc")
        assert list(item) == ["a", "b", "c"]

    def test_hash(self):
        item = Item("hello")
        d = {item: "value"}
        assert d[item] == "value"

    def test_original_str(self):
        item = Item("hello")
        assert item.original == "hello"
        assert isinstance(item.original, str)

    def test_original_none(self):
        item = Item(None)
        assert item.original is None

    def test_integer_from_digit_string(self):
        item = Item("42")
        assert item.integer == 42

    def test_integer_non_digit_returns_none(self):
        item = Item("hello")
        assert item.integer is None

    def test_iadd(self):
        item = Item("hello")
        item += " world"
        assert item.string == "hello world"

    def test_replace(self):
        item = Item("hello world")
        result = item.replace("world", "there")
        assert result == b"hello there"

    def test_bool_truthy(self):
        item = Item("nonempty")
        assert bool(item) is True

    def test_str_dunder(self):
        item = Item("hello")
        assert str(item) == "hello"

    def test_byte_item_bool_handled_as_int(self):
        result = Item.byte_item(True)
        assert result == b"1"

    def test_byte_item_false(self):
        result = Item.byte_item(False)
        assert result == b"0"

    def test_boolean_from_bytes_nonempty(self):
        item = Item(b"hello")
        assert item.boolean is True

    def test_boolean_from_bytes_empty(self):
        item = Item(b"")
        assert item.boolean is False


class Test_ObjectDict:
    def test_attribute_access(self):
        d = ObjectDict({"hello": "world"})
        assert d.hello == "world"

    def test_attribute_set(self):
        d = ObjectDict()
        d.hello = "world"
        assert d["hello"] == "world"

    def test_standard_getitem(self):
        d = ObjectDict({"key": "val"})
        assert d["key"] == "val"

    def test_setitem_then_getattr(self):
        d = ObjectDict()
        d["foo"] = "bar"
        assert d.foo == "bar"


class Test_OverloadedDict:
    def test_add_merges(self):
        d1 = OverloadedDict({"a": 1})
        d2 = {"b": 2}
        result = d1 + d2
        assert result["a"] == 1
        assert result["b"] == 2

    def test_iadd_merges_inplace(self):
        d = OverloadedDict({"a": 1})
        d += {"b": 2}
        assert "b" in d

    def test_sub_removes_matching(self):
        d1 = OverloadedDict({"a": 1, "b": 2})
        d2 = {"a": 1}
        result = d1 - d2
        assert "a" not in result
        assert result["b"] == 2

    def test_isub_removes_inplace(self):
        d = OverloadedDict({"a": 1, "b": 2})
        d -= {"a": 1}
        assert "a" not in d

    def test_add_returns_overloaded_dict(self):
        d1 = OverloadedDict({"x": 1})
        result = d1 + {"y": 2}
        assert isinstance(result, OverloadedDict)

    def test_sub_does_not_remove_value_mismatch(self):
        d1 = OverloadedDict({"a": 1, "b": 2})
        d2 = {"a": 99}
        result = d1 - d2
        assert "a" in result


class Test_UnderscoreAccessDict:
    def test_underscore_access(self):
        d = UnderscoreAccessDict({"content type": "text/html"})
        assert d["content_type"] == "text/html"

    def test_space_access(self):
        d = UnderscoreAccessDict({"content_type": "text/html"})
        assert d["content_type"] == "text/html"

    def test_bytes_key_with_underscore(self):
        d = UnderscoreAccessDict({b"content type": "text/html"})
        assert d[b"content_type"] == "text/html"

    def test_direct_key_fallback(self):
        d = UnderscoreAccessDict({"hello": "world"})
        assert d["hello"] == "world"

    def test_bytes_direct_key(self):
        d = UnderscoreAccessDict({b"x": "y"})
        assert d[b"x"] == "y"


class Test_MultiEntryDict:
    def test_first_set_is_value(self):
        d = MultiEntryDict()
        d["key"] = "first"
        assert d["key"] == "first"

    def test_second_set_creates_list(self):
        d = MultiEntryDict()
        d["key"] = "first"
        d["key"] = "second"
        assert isinstance(d["key"], list)
        assert "first" in d["key"]
        assert "second" in d["key"]

    def test_third_set_appends_to_list(self):
        d = MultiEntryDict()
        d["key"] = "a"
        d["key"] = "b"
        d["key"] = "c"
        assert len(d["key"]) == 3
        assert "c" in d["key"]

    def test_different_keys_independent(self):
        d = MultiEntryDict()
        d["x"] = "1"
        d["y"] = "2"
        assert d["x"] == "1"
        assert d["y"] == "2"


class Test_ItemDict:
    def test_values_wrapped_in_item(self):
        d = ItemDict({"key": "value"})
        assert isinstance(d["key"], Item)
        assert d["key"] == "value"

    def test_type_agnostic_key_access(self):
        d = ItemDict({"42": "forty-two"})
        assert d["42"] == "forty-two"
        assert d[42] == "forty-two"
        assert d[b"42"] == "forty-two"

    def test_setitem_wraps_value(self):
        d = ItemDict()
        d["key"] = "value"
        assert isinstance(d["key"], Item)

    def test_list_values_wrapped(self):
        d = ItemDict({"accept": ["text/html", "application/json"]})
        assert isinstance(d["accept"], list)
        assert all(isinstance(v, Item) for v in d["accept"])

    def test_contains(self):
        d = ItemDict({"hello": "world"})
        assert "hello" in d
        assert b"hello" in d

    def test_update(self):
        d = ItemDict({"a": "1"})
        d.update({"b": "2"})
        assert d["b"] == "2"
        assert isinstance(d["b"], Item)

    def test_delitem(self):
        d = ItemDict({"key": "val"})
        del d["key"]
        assert "key" not in d

    def test_empty_init(self):
        d = ItemDict()
        assert len(d) == 0

    def test_kwargs_init(self):
        d = ItemDict(foo="bar")
        assert d["foo"] == "bar"
        assert isinstance(d["foo"], Item)

    def test_setitem_list_value(self):
        d = ItemDict()
        d["headers"] = ["a", "b"]
        assert isinstance(d["headers"], list)
        assert all(isinstance(v, Item) for v in d["headers"])
