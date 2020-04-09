from mitm import color
import requests


def get_ip(protocol):
    return requests.get(
        f"{protocol}://api.ipify.org?format=json",
        proxies={"http": "127.0.0.1:8888", "https": "127.0.0.1:8888"},
        verify=False,
    ).text


print(color.green("HTTP Reply:\n"), get_ip(protocol="http"), "\n")
print(color.green("HTTPS Reply:\n"), get_ip(protocol="https"))
