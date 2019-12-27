import select
import socket
import ssl

from .request import HTTPRequest

socket.setdefaulttimeout(3)


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

    def send_request(self, connect, data):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Parses the data.
        data_request = HTTPRequest(data)

        if connect:
            connect_request = HTTPRequest(connect)
            path = connect_request.path.split(":")
            sever_address = (path[0], int(path[1]))

            sock.connect(sever_address)
            sock = ssl.wrap_socket(
                sock,
                keyfile=None,
                certfile=None,
                server_side=False,
                cert_reqs=ssl.CERT_NONE,
                ssl_version=ssl.PROTOCOL_SSLv23,
            )
        else:
            server_address = (data_request.headers["HOST"], 80)
            sock.connect(server_address)

        sock.send(data)

        resp = b""

        while True:
            try:
                buf = sock.recv(1024)
                if not buf:
                    break
                else:
                    resp += buf
            except Exception as e:
                print("ERROR!!", e)
                break

        return resp
