import os
import socket
import unittest
from unittest import mock

from upcomarr.http import Client, FetchError

from . import fixtures
from .fakearr import FakeArr, Recorder


def closed_port_url() -> str:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"


class ClientTest(unittest.TestCase):
    def test_sends_key_as_header(self):
        with FakeArr([{"x": 1}]) as arr:
            data = Client(arr.url, fixtures.API_KEY, 5).get_json("/api/v3/calendar")
            self.assertEqual(data, [{"x": 1}])
            path, headers = arr.requests[0]
            self.assertEqual(headers.get("X-Api-Key"), fixtures.API_KEY)
            self.assertNotIn(fixtures.API_KEY, path)

    def test_refuses_redirects_and_never_forwards_the_key(self):
        target = Recorder()
        try:
            with FakeArr() as arr:
                arr.redirect_to = target.url + "/stolen"
                with self.assertRaises(FetchError) as ctx:
                    Client(arr.url, fixtures.API_KEY, 5).get_json("/api/v3/calendar")
                self.assertEqual(ctx.exception.code, "redirect")
            self.assertEqual(target.requests, [])
        finally:
            target.close()

    def test_ignores_proxy_environment(self):
        proxy = Recorder()
        try:
            env = {"HTTP_PROXY": proxy.url, "http_proxy": proxy.url, "HTTPS_PROXY": proxy.url, "NO_PROXY": ""}
            with mock.patch.dict(os.environ, env), FakeArr([]) as arr:
                Client(arr.url, fixtures.API_KEY, 5).get_json("/api/v3/calendar")
                self.assertEqual(len(arr.requests), 1)
            self.assertEqual(proxy.requests, [])
        finally:
            proxy.close()

    def test_error_codes(self):
        with FakeArr() as arr:
            with self.assertRaises(FetchError) as ctx:
                Client(arr.url, fixtures.OTHER_KEY, 5).get_json("/api/v3/calendar")
            self.assertEqual(ctx.exception.code, "http_401")
            arr.fail_status = 503
            with self.assertRaises(FetchError) as ctx:
                Client(arr.url, fixtures.API_KEY, 5).get_json("/api/v3/calendar")
            self.assertEqual(ctx.exception.code, "http_503")
            arr.fail_status = None
            arr.body_override = b"<html>not json"
            with self.assertRaises(FetchError) as ctx:
                Client(arr.url, fixtures.API_KEY, 5).get_json("/api/v3/calendar")
            self.assertEqual(ctx.exception.code, "bad_json")
        with self.assertRaises(FetchError) as ctx:
            Client(closed_port_url(), fixtures.API_KEY, 2).get_json("/api/v3/calendar")
        self.assertEqual(ctx.exception.code, "connect")

    def test_size_cap(self):
        with FakeArr() as arr:
            arr.poster_bytes = fixtures.JPEG * 100
            with self.assertRaises(FetchError) as ctx:
                Client(arr.url, fixtures.API_KEY, 5).get_bytes("/api/v3/mediacover/1/poster-250.jpg", max_bytes=500)
            self.assertEqual(ctx.exception.code, "too_large")

    def test_timeout(self):
        with FakeArr([]) as arr:
            arr.delay = 1.5
            with self.assertRaises(FetchError) as ctx:
                Client(arr.url, fixtures.API_KEY, 0.5).get_json("/api/v3/calendar")
            self.assertEqual(ctx.exception.code, "timeout")

    def test_errors_never_carry_the_key(self):
        with FakeArr() as arr:
            arr.fail_status = 500
            try:
                Client(arr.url, fixtures.API_KEY, 5).get_json("/api/v3/calendar")
            except FetchError as e:
                self.assertEqual(str(e), "http_500")
                self.assertIsNone(e.__cause__)
                self.assertTrue(e.__suppress_context__)
        self.assertNotIn(fixtures.API_KEY, repr(Client("http://x", fixtures.API_KEY, 1)))


if __name__ == "__main__":
    unittest.main()
