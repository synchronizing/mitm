###############
Trusting `mitm`
###############

The first time `mitm` runs it generates a `certificate authority <https://en.wikipedia.org/wiki/Certificate_authority>`_ (CA) that is used to generate dummy certificates for each website visited, and reuses it after that. To trust this certificate you must install it on your system. By default, the certificate is generated in the `mitm.__data__` directory. To discover what this directory is do the following:

.. code-block:: shell

    $ python
    >>> import mitm
    >>> mitm.__data__
    PosixPath('/Users/felipe/Library/Application Support/mitm') # You should see a different path.
    >>> exit()
    
    $ ls /Users/felipe/Library/Application\ Support/mitm
    mitm.key mitm.pem

Note that commands wrapped with the command line (``mitm -- <command>``) trust the certificate automatically, as long as they respect the ``SSL_CERT_FILE``, ``REQUESTS_CA_BUNDLE``, ``CURL_CA_BUNDLE``, ``NODE_EXTRA_CA_CERTS``, ``DENO_CERT``, ``GIT_SSL_CAINFO``, or ``AWS_CA_BUNDLE`` environment variables.
    
Customizing Path
----------------

To customize the path where the certificate is generated, you can use the following snippet:

.. code-block:: python

    from mitm import MITM, CertificateAuthority, middleware, protocol
    from pathlib import Path

    # Loads the CA certificate.
    path = Path("/Users/felipe/Desktop")
    certificate_authority = CertificateAuthority.init(path=path)

    # Starts the MITM server.
    mitm = MITM(
        host="127.0.0.1",
        port=8888,
        protocols=[protocol.HTTP],
        middlewares=[middleware.HTTPLog],
        certificate_authority=certificate_authority,
    )
    mitm.run()

Installing CA
--------------

While `mitm` is running, browse to its address (``http://localhost:8888`` by default) to download the certificate. The page has the certificate in the formats used by each system (iOS, Android, macOS, Windows, and Linux), with instructions on how to install it.
