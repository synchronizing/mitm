from termcolor import colored
import asyncio
import aiohttp


async def get_ip(protocol):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{protocol}://api.ipify.org?format=json",
            ssl=False,
            proxy="http://127.0.0.1:8888",
        ) as response:
            return await response.text()


print(colored("HTTP Reply:\n", "green"), asyncio.run(get_ip(protocol="http")), "\n")
print(colored("HTTPS Reply:\n", "green"), asyncio.run(get_ip(protocol="https")))
