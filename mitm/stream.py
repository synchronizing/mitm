from http_parser.parser import HttpParser
import asyncio
import aiohttp


class EmulatedClient(object):
    """ Class for emulating the client to the server.

        Notes:
            To accomplish a proper man-in-the-middle attack with TLS capability,
            the man-in-the-middle must be the one sending the original request to
            the server. With the emulated client we are changing the typical structure:

                client <-> server

            To one that looks like so:

                client <-> mitm (server) <-> mitm (emulated client) <-> server

            Where we then reply back to the client with the response the emulated client
            retrieved from the server on behalf of the client.
    """

    def __init__(self, using_ssl):
        # Creates our HttpParser object.
        self.http_parser = HttpParser()

        # Sets flag to whether or not we are using SSL.
        self.using_ssl = using_ssl

    async def connect(self, data):
        # Parses the data coming in.
        self.http_parser.execute(data, len(data))

        host = self.http_parser.get_wsgi_environ()["HTTP_HOST"]
        uri = self.http_parser.get_wsgi_environ()["RAW_URI"]

        # Sets the proper URL client is trying to reach.
        if self.using_ssl:
            url = f"https://{host}:{uri}"
        else:
            url = uri

        # Retrieves the destination server data.
        async with aiohttp.ClientSession() as session:
            async with session.get(url, ssl=False) as response:
                status = response.status
                reason = response.reason
                headers = response.headers
                response = await response.read()

        resp = f"HTTP/1.1 {status} {reason}\r\n".encode("latin-1")

        for header in headers:
            resp += f"{header}: {headers[header]}\r\n".encode("latin-1")

        resp += b"\r\n" + response

        # Returns the data.
        return resp

    async def _connect(self, data):
        # Parses the data coming in.
        self.http_parser.execute(data, len(data))

        # Creates the connection to the data server.
        self.reader, self.writer = await asyncio.open_connection(
            self.http_parser.get_headers()["HOST"], 80
        )

        # Shoots the query over.
        self.writer.write(data)

        # Tell the client that this is the end of our data.
        self.writer.write_eof()

        # Gets the corresponding reply from the server.
        line = b""
        while True:
            curr_line = await self.reader.readline()
            if not curr_line:
                break
            line += curr_line

        # Closes the writer.
        self.writer.close()

        # Returns the data.
        return line
