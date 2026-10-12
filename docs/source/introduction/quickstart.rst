##########
Quickstart
##########

Man-in-the-middle proxy for HTTP and HTTPS.

----

Installing
----------

.. code-block::

    pip install mitm

Command line
------------

Run a command through the proxy to see every request it makes:

.. code-block::

    $ mitm -- curl -s https://api.github.com/zen
      ┊ GET https://api.github.com/zen → 200 OK (text/plain, 35 B, 45 ms)
    Approachable is better than simple.

.. code-block::

    mitm -- curl https://example.com          # one line per request
    mitm -v -- python app.py                  # include headers and bodies
    mitm --json -o traffic.jsonl -- npm ci    # every exchange as JSON Lines
    mitm                                      # standalone proxy on 127.0.0.1:8888

The command runs with ``HTTP_PROXY`` and ``HTTPS_PROXY`` pointing at the proxy, and
with ``SSL_CERT_FILE``, ``REQUESTS_CA_BUNDLE``, ``NODE_EXTRA_CA_CERTS`` (and similar)
pointing at its certificate authority. Its exit code is passed through. Run
``mitm --help`` for every option.

Library
-------

.. code-block:: python

    from mitm import MITM, HTTPLog, Middleware, CertificateAuthority, protocol

    mitm = MITM(
        host="127.0.0.1",
        port=8888,
        protocols=[protocol.HTTP],
        middlewares=[HTTPLog],
        certificate_authority=CertificateAuthority.init("/path/to/ca"),
    )
    mitm.run()

Every argument above is optional. By default the proxy listens on ``127.0.0.1:8888``,
logs each exchange to stderr, and uses the certificate authority stored in
``mitm.__data__``. The proxy also works as an async context manager:

.. code-block:: python

    async with MITM(port=0) as proxy:  # Port 0 picks a free port.
        print(proxy.port)

Questions & Answers
--------------------

**How does this project differ from** ``mitmproxy`` **?**

Purpose, implementation, and customization style. ``mitm`` is a lightweight proxy with
two dependencies, meant to be embedded in larger projects or to answer "what does this
command send?" in one line. ``mitmproxy`` does everything ``mitm`` does and much more,
at the cost of that simplicity.

**What protocols are supported out-of-the-box?**

HTTP/1.0 and HTTP/1.1, with or without TLS. Protocols that upgrade from HTTP/1.1 (such
as WebSockets) are relayed, but only the upgrade request is logged. Anything else (HTTP/2
only clients, FTP, SMTP, etc.) requires a custom `mitm.models.Protocol`.
