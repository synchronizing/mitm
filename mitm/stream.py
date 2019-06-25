from http_parser.parser import HttpParser
import asyncio


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

    def __init__(self):
        # Creates our HttpParser object.
        self.http_parser = HttpParser()

    async def connect(self, data):
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
