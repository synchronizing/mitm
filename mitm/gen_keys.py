from OpenSSL import crypto
from socket import gethostname
import os


def create_self_signed_cert():

    # Creates key pair.
    k = crypto.PKey()
    k.generate_key(crypto.TYPE_RSA, 1024)

    # Creates self-signed certificate.
    cert = crypto.X509()
    cert.get_subject().C = "US"
    cert.get_subject().ST = "New York"
    cert.get_subject().L = "New York"
    cert.get_subject().O = "."
    cert.get_subject().OU = "."
    cert.get_subject().CN = gethostname()
    cert.set_serial_number(1000)
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(10 * 365 * 24 * 60 * 60)
    cert.set_issuer(cert.get_subject())
    cert.set_pubkey(k)
    cert.sign(k, "sha1")

    if not os.path.exists("ssl"):
        os.makedirs("ssl")

    with open("ssl/server.crt", "wb") as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))

    with open("ssl/server.key", "wb") as f:
        f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k))
