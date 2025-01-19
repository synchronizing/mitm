###############
Trusting `mitm`
###############

When `mitm` runs it generates a `certificate authority <https://en.wikipedia.org/wiki/Certificate_authority>`_ (CA) that is used to generate dummy certificates for each website visited. To trust this certificate you must install it on your system. By default, the certificate is generated in the `mitm.__data__` directory. To discover what this directory is do the following:

.. code-block:: shell

    $ python
    Python 3.9.6 (default, Aug 31 2021, 00:19:31) 
    [Clang 12.0.5 (clang-1205.0.22.11)] on darwin
    Type "help", "copyright", "credits" or "license" for more information.
    >>> import mitm
    >>> mitm.__data__
    PosixPath('/Users/felipe/Library/Application Support/mitm') # You should see a different path.
    >>> exit()
    
    $ ls /Users/felipe/Library/Application\ Support/mitm
    mitm.key mitm.pem
    
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
        middlewares=[middleware.Log],
        certificate_authority=certificate_authority,
    )
    mitm.run()

Installing CA
--------------

Different systems have different ways to install the certificate. Its recommended you look up "how to install a certificate" on your system.
