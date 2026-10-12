###############
Trusting `mitm`
###############

To read HTTPS traffic `mitm` presents its own certificate for every website, signed by
its `certificate authority <https://en.wikipedia.org/wiki/Certificate_authority>`_ (CA).
Clients only accept those certificates if they trust that CA.

The CA is created on first use and stored in `mitm.__data__`, as ``mitm.pem`` (the
certificate) and ``mitm.key`` (its private key, readable only by you):

.. code-block:: shell

    $ python -c "import mitm; print(mitm.__data__)"
    /Users/felipe/Library/Application Support/mitm

Command line
------------

Commands run through ``mitm -- <command>`` trust the CA automatically, through the
``SSL_CERT_FILE``, ``REQUESTS_CA_BUNDLE``, ``CURL_CA_BUNDLE``, ``NODE_EXTRA_CA_CERTS``,
``DENO_CERT``, ``GIT_SSL_CAINFO``, and ``AWS_CA_BUNDLE`` environment variables.

Installing the CA
-----------------

Clients that only use the system's trust store (browsers, Java, Go on macOS, phones)
need the CA installed. While `mitm` runs, open its address (``http://127.0.0.1:8888/``
by default) in a browser to download the certificate in the right format, with
instructions for iOS, Android, macOS, Windows, and Linux.

Custom location
---------------

.. code-block:: python

    from mitm import MITM, CertificateAuthority

    certificate_authority = CertificateAuthority.init(path="/path/to/ca")
    MITM(certificate_authority=certificate_authority).run()

`mitm.crypto.CertificateAuthority.init` loads the CA stored in the directory, or
creates one there if it's missing, expired, or its key does not match.
