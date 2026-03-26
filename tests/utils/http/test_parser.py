import typing

import pytest

from mitm.utils.http.parser import Headers, Request, Response, state


class Test_Headers:
    def test_compile_single_header(self):
        h = Headers({"Content-Type": "text/html"})
        raw = h._compile()
        assert raw == b"Content-Type: text/html\r\n\r\n"

    def test_compile_multiple_headers(self):
        h = Headers({"A": "1", "B": "2"})
        raw = h._compile()
        assert b"A: 1\r\n" in raw
        assert b"B: 2\r\n" in raw
        assert raw.endswith(b"\r\n")

    def test_compile_empty_headers(self):
        h = Headers()
        raw = h._compile()
        assert raw == b"\r\n"

    def test_setitem_replaces_existing(self):
        h = Headers({"Host": "old.com"})
        h["Host"] = "new.com"
        assert h["Host"] == "new.com"
        assert len([k for k in h if str(k) == "Host"]) == 1

    def test_setitem_adds_new_key(self):
        h = Headers({"Host": "example.com"})
        h["Content-Type"] = "text/html"
        assert h["Content-Type"] == "text/html"
        assert len(h) == 2

    def test_defaultsetitem_keeps_both(self):
        h = Headers()
        h.__defaultsetitem__("Accept", "text/html")
        h.__defaultsetitem__("Accept", "application/json")
        assert "Accept" in h

    def test_compile_with_list_value(self):
        h = Headers()
        h.__defaultsetitem__("Accept", "text/html")
        h.__defaultsetitem__("Accept", "application/json")
        raw = h._compile()
        assert b"text/html" in raw
        assert b"application/json" in raw

    def test_raw_property_equals_compile(self):
        h = Headers({"X-Foo": "bar"})
        assert h.raw == h._compile()

    def test_contains_key(self):
        h = Headers({"Host": "example.com"})
        assert "Host" in h
        assert "Missing" not in h

    def test_header_value_accessible_by_string_key(self):
        h = Headers({"Content-Length": "42"})
        assert h["Content-Length"] == "42"


class Test_Request:
    RAW_SIMPLE = b"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"
    RAW_WITH_BODY = b"POST /submit HTTP/1.1\r\nContent-Length: 5\r\n\r\nhello"

    def test_parse_simple(self):
        msg = Request.parse(self.RAW_SIMPLE)
        assert isinstance(msg, Request)
        assert msg.method == "GET"
        assert msg.target == "/"
        assert msg.protocol == "HTTP/1.1"
        assert msg.headers["Host"] == "example.com"

    def test_parse_with_body(self):
        msg = Request.parse(self.RAW_WITH_BODY)
        assert isinstance(msg, Request)
        assert msg.method == "POST"
        assert msg.target == "/submit"
        assert msg.body == "hello"

    def test_compile_round_trip(self):
        req = Request.parse(self.RAW_SIMPLE)
        assert req._compile() == self.RAW_SIMPLE

    def test_compile_round_trip_with_body(self):
        req = Request.parse(self.RAW_WITH_BODY)
        assert req._compile() == self.RAW_WITH_BODY

    def test_equality(self):
        r1 = Request.parse(self.RAW_SIMPLE)
        r2 = Request.parse(self.RAW_SIMPLE)
        assert r1 == r2

    def test_inequality(self):
        r1 = Request.parse(self.RAW_SIMPLE)
        r2 = Request.parse(self.RAW_WITH_BODY)
        assert r1 != r2

    def test_str_has_arrow(self):
        req = Request.parse(self.RAW_SIMPLE)
        s = str(req)
        assert "→" in s

    def test_raw_property(self):
        req = Request.parse(self.RAW_SIMPLE)
        assert req.raw == self.RAW_SIMPLE

    def test_partial_args_raises(self):
        with pytest.raises(ValueError):
            Request(method="GET")

    def test_partial_args_raises_target_only(self):
        with pytest.raises(ValueError):
            Request(target="/path")

    def test_no_args_succeeds(self):
        req = Request()
        assert req.buffer == b""

    def test_all_args_sets_buffer(self):
        req = Request(method="GET", target="/", protocol="HTTP/1.1")
        assert b"GET / HTTP/1.1\r\n" in req.buffer

    def test_feed_incremental(self):
        req = Request()
        result = req.feed(b"GET / HTTP/1.1\r\n")
        assert result == state.HEADER
        result = req.feed(b"Host: example.com\r\n\r\n")
        assert result == state.BODY

    def test_feed_non_bytes_raises(self):
        req = Request()
        bad = typing.cast(bytes, "not bytes")
        with pytest.raises(TypeError):
            req.feed(bad)

    def test_feed_integer_raises(self):
        req = Request()
        bad = typing.cast(bytes, 42)
        with pytest.raises(TypeError):
            req.feed(bad)

    def test_state_incomplete_top(self):
        req = Request()
        req.feed(b"GET /")
        assert req.state == state.TOP

    def test_state_header_mid_parse(self):
        req = Request()
        req.feed(b"GET / HTTP/1.1\r\n")
        assert req.state == state.HEADER

    def test_state_body_complete(self):
        req = Request()
        req.feed(self.RAW_SIMPLE)
        assert req.state == state.BODY

    def test_parse_multiple_headers(self):
        raw = b"GET / HTTP/1.1\r\nHost: example.com\r\nAccept: text/html\r\n\r\n"
        msg = Request.parse(raw)
        assert msg.headers["Host"] == "example.com"
        assert msg.headers["Accept"] == "text/html"

    def test_header_with_colon_in_value(self):
        raw = b"GET / HTTP/1.1\r\nLocation: http://host:8080/path\r\n\r\n"
        msg = Request.parse(raw)
        location = msg.headers["Location"].string
        assert "host" in location or "8080" in location

    def test_parse_connect_method(self):
        raw = b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n"
        msg = Request.parse(raw)
        assert isinstance(msg, Request)
        assert msg.method == "CONNECT"
        assert msg.target == "example.com:443"

    def test_state_enum_values(self):
        assert state.TOP.value == 0
        assert state.HEADER.value == 1
        assert state.BODY.value == 2

    def test_comma_separated_header_value(self):
        raw = b"GET / HTTP/1.1\r\nAccept: text/html, application/json\r\n\r\n"
        msg = Request.parse(raw)
        assert "Accept" in msg.headers


class Test_Response:
    RAW_SIMPLE = b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"
    RAW_WITH_BODY = b"HTTP/1.1 404 Error\r\nContent-Length: 9\r\n\r\nnot found"

    def test_parse_simple(self):
        msg = Response.parse(self.RAW_SIMPLE)
        assert isinstance(msg, Response)
        assert msg.protocol == "HTTP/1.1"
        assert msg.status == "200"
        assert msg.reason == "OK"

    def test_parse_with_body(self):
        msg = Response.parse(self.RAW_WITH_BODY)
        assert isinstance(msg, Response)
        assert msg.status == "404"
        assert msg.body == "not found"

    def test_parse_header(self):
        msg = Response.parse(self.RAW_SIMPLE)
        assert msg.headers["Content-Type"] == "text/html"

    def test_compile_round_trip(self):
        resp = Response.parse(self.RAW_SIMPLE)
        assert resp._compile() == self.RAW_SIMPLE

    def test_compile_round_trip_with_body(self):
        resp = Response.parse(self.RAW_WITH_BODY)
        assert resp._compile() == self.RAW_WITH_BODY

    def test_equality(self):
        r1 = Response.parse(self.RAW_SIMPLE)
        r2 = Response.parse(self.RAW_SIMPLE)
        assert r1 == r2

    def test_inequality(self):
        r1 = Response.parse(self.RAW_SIMPLE)
        r2 = Response.parse(self.RAW_WITH_BODY)
        assert r1 != r2

    def test_str_has_arrow(self):
        resp = Response.parse(self.RAW_SIMPLE)
        s = str(resp)
        assert "←" in s

    def test_raw_property(self):
        resp = Response.parse(self.RAW_SIMPLE)
        assert resp.raw == self.RAW_SIMPLE

    def test_partial_args_raises(self):
        with pytest.raises(ValueError):
            Response(status="200")

    def test_partial_args_raises_protocol_only(self):
        with pytest.raises(ValueError):
            Response(protocol="HTTP/1.1")

    def test_no_args_succeeds(self):
        resp = Response()
        assert resp.buffer == b""

    def test_all_args_sets_buffer(self):
        resp = Response(protocol="HTTP/1.1", status="200", reason="OK")
        assert b"HTTP/1.1 200 OK\r\n" in resp.buffer

    def test_feed_incremental(self):
        resp = Response()
        result = resp.feed(b"HTTP/1.1 200 OK\r\n")
        assert result == state.HEADER
        result = resp.feed(b"Content-Type: text/html\r\n\r\n")
        assert result == state.BODY

    def test_feed_non_bytes_raises(self):
        resp = Response()
        bad = typing.cast(bytes, "not bytes")
        with pytest.raises(TypeError):
            resp.feed(bad)

    def test_state_top_before_crlf(self):
        resp = Response()
        resp.feed(b"HTTP/1.1 200")
        assert resp.state == state.TOP

    def test_state_header_mid_parse(self):
        resp = Response()
        resp.feed(b"HTTP/1.1 200 OK\r\n")
        assert resp.state == state.HEADER

    def test_state_body_complete(self):
        resp = Response()
        resp.feed(self.RAW_SIMPLE)
        assert resp.state == state.BODY

    def test_parse_301_redirect(self):
        raw = b"HTTP/1.1 301 Moved\r\nLocation: https://example.com\r\n\r\n"
        msg = Response.parse(raw)
        assert isinstance(msg, Response)
        assert msg.status == "301"
        assert msg.reason == "Moved"

    def test_parse_500_error(self):
        raw = b"HTTP/1.1 500 Error\r\n\r\n"
        msg = Response.parse(raw)
        assert isinstance(msg, Response)
        assert msg.status == "500"
        assert msg.protocol == "HTTP/1.1"
