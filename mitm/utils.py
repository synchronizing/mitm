""" Man in the middle utilities module.

This module contains useful tools that mitm utilizes to accomplish its goal. This
includes an HTTP request parser, an API to generate RSA certificate/key pair, and
printing color.
"""

from http.server import BaseHTTPRequestHandler
from io import BytesIO
from OpenSSL import crypto
from socket import gethostname
import os


class HTTPRequest(BaseHTTPRequestHandler):
    """ Parses HTTP/HTTPS requests for easy interpolation.

    Note:
        https://docs.python.org/3/library/http.server.html#http.server.BaseHTTPRequestHandler
    """

    def __init__(self, request_text):
        """ Initializes the HTTPRequest.

        Args:
            request_text (bytes): String with the HTTP request.
        """

        self.rfile = BytesIO(request_text)
        self.raw_requestline = self.rfile.readline()
        self.error_code = self.error_message = None
        self.parse_request()

    def send_error(self, code, message):
        self.error_code = code
        self.error_message = message


class RSA:
    """ A simple API to generate RSA's certificate/private key pairs.

    Attributes:
        private_key_obj (crypto.PKey): Private key object.
        certificate_obj (crypto.X509): Certificate object.
        private_key (io.BytesIO): Memory file with private key dump.
        certificate (io.BytesIO): Memory file with certificate dump.
        private_key_file (str): Path to private key file.
        certificate_file (str): Path to certificate file.
    """

    def __init__(self, dir=None):
        """ Initializes an RSA key pair.

        Args:
            dir (str): Directory to save key pair. If none is given, /tmp/mitm is used.
        """

        # Pubkey
        self.private_key_obj = crypto.PKey()
        self.private_key_obj.generate_key(crypto.TYPE_RSA, 1024)

        # Certificate info.
        self.certificate_obj = crypto.X509()
        self.certificate_obj.get_subject().C = "US"
        self.certificate_obj.get_subject().ST = "New York"
        self.certificate_obj.get_subject().L = "New York"
        self.certificate_obj.get_subject().O = "."
        self.certificate_obj.get_subject().OU = "."
        self.certificate_obj.get_subject().CN = gethostname()
        self.certificate_obj.set_serial_number(1000)
        self.certificate_obj.gmtime_adj_notBefore(0)
        self.certificate_obj.gmtime_adj_notAfter(10 * 365 * 24 * 60 * 60)

        # Setting certificate/privkey.
        self.certificate_obj.set_issuer(self.certificate_obj.get_subject())
        self.certificate_obj.set_pubkey(self.private_key_obj)
        self.certificate_obj.sign(self.private_key_obj, "sha1")

        # .crt and .key file dump.
        cert = crypto.dump_certificate(crypto.FILETYPE_PEM, self.certificate_obj)
        privkey = crypto.dump_privatekey(crypto.FILETYPE_PEM, self.private_key_obj)

        # Saves to "memory file."
        self.certificate = BytesIO(cert)
        self.private_key = BytesIO(privkey)

        # If dir is not passed, saves the certificate in /tmp/.
        if dir:
            self.save(dir)
        else:
            self.save("/tmp/mitm/")

    def save(self, dir):
        """ Saves the the key pair.

        Args:
            dir (str): Path to save key pair.
        """

        if not os.path.exists(dir):
            os.makedirs(dir)

        self.certificate_file = f"{dir}/mitm.crt"
        self.private_key_file = f"{dir}/mitm.key"

        with open(self.certificate_file, "wb") as f:
            f.write(self.certificate.getbuffer())

        with open(self.private_key_file, "wb") as f:
            f.write(self.private_key.getbuffer())


class color:
    """ Allows the printing of color in console.

    Note:
        To use this class simply refer to the colors below as so:

            print(color.red("String in here."))
    """

    reset = "\u001b[0m"

    @staticmethod
    def red(text):
        return f"\033[1;31;40m{text}" + color.reset

    @staticmethod
    def green(text):
        return f"\033[1;32;40m{text}" + color.reset

    @staticmethod
    def yellow(text):
        return f"\033[1;33;40m{text}" + color.reset

    @staticmethod
    def blue(text):
        return f"\033[1;34;40m{text}" + color.reset

    @staticmethod
    def purple(text):
        return f"\033[1;35;40m{text}" + color.reset

    @staticmethod
    def cyan(text):
        return f"\033[1;36;40m{text}" + color.reset

    @staticmethod
    def white(text):
        return f"\033[1;37;40m{text}" + color.reset
