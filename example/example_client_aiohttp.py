from mitm import color
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


print(color.green("HTTP Reply:\n"), asyncio.run(get_ip(protocol="http")), "\n")
print(color.green("HTTPS Reply:\n"), asyncio.run(get_ip(protocol="https")))
