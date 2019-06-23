from mitm import ManInTheMiddle
import asyncio

mitm = ManInTheMiddle(host="127.0.0.1", port=8080)
asyncio.run(mitm.start())
