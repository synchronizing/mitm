from mitm.server import ManInTheMiddle
import asyncio

mitm = ManInTheMiddle(data=b"Server reply! (HTTP or HTTPS)\n")
asyncio.run(mitm.start_server())
