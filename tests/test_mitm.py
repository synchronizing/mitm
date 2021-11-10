import multiprocessing
import time
import toolbox

import pytest
import requests
from mitm import MITM, Config


@pytest.fixture(autouse=True)
async def server():

    p = multiprocessing.Process(target=MITM.start)
    p.start()
    time.sleep(1)  # Give enough time for the server to start.
    yield
    p.terminate()


class Test_mitm:
    def test_http_request(self, server):
        requests.packages.urllib3.disable_warnings()

        r1 = requests.get(
            "http://example.com",
            proxies={"http": "http://127.0.0.1:8888", "https": "http://127.0.0.1:8888"},
            verify=False,
        )

        r2 = requests.get("http://example.com")
        assert r1.text == r2.text

    def test_https_request(self, server):
        requests.packages.urllib3.disable_warnings()

        r1 = requests.get(
            "https://example.com",
            proxies={"http": "http://127.0.0.1:8888", "https": "http://127.0.0.1:8888"},
            verify=False,
        )

        r2 = requests.get("https://example.com")
        assert r1.text == r2.text
