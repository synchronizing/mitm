from http_parser.parser import HttpParser
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

        # Re-creates the servers response.
        resp = f"HTTP/1.1 {status} {reason}\r\n".encode("latin-1")
        for header in headers:
            resp += f"{header}: {headers[header]}\r\n".encode("latin-1")
        resp += b"\r\n" + response

        # Returns the data.
        return resp
