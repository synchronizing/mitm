import requests
from termcolor import colored


def get_ip(protocol):
    return requests.get(
        f"{protocol}://api.ipify.org?format=json",
        proxies={"http": "127.0.0.1:8888", "https": "127.0.0.1:8888"},
        verify=False,
    ).text


print(colored("HTTP Reply:\n", "green"), get_ip(protocol="http"), "\n")
print(colored("HTTPS Reply:\n", "green"), get_ip(protocol="https"))
