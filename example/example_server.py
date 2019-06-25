from mitm import ManInTheMiddle
import asyncio

mitm = ManInTheMiddle(host="127.0.0.1", port=8888)
asyncio.run(mitm.start())
