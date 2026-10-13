##########
Quickstart
##########

A customizable man-in-the-middle TCP proxy with support for HTTP & HTTPS.

----

Installing
----------

.. code-block::
    
    pip install mitm

Note that OpenSSL 1.1.1 or greater is required.

Using
-----

Using the default values for the :py:class:`mitm.MITM` class:

.. code-block:: python

    from mitm import MITM, protocol, middleware

    mitm = MITM(
        host="127.0.0.1",
        port=8888,
        protocols=[protocol.HTTP],
        middlewares=[middleware.HTTPLog],
    )
    mitm.run()

This will start a proxy on port `8888` that is capable of intercepting all HTTP traffic (with support for SSL/TLS) and log all activity.

Command line
------------

`mitm` can also wrap any command and log the HTTP & HTTPS requests it makes:

.. code-block::

    $ mitm -- curl -s https://api.github.com/zen
      ┊ GET https://api.github.com/zen → 200 OK (text/plain, 19 B, 44 ms)
    Accessible for all.

The `┊` lines are the intercepted traffic (stderr). Everything else is the command's normal output (stdout). `mitm` sets ``HTTP_PROXY``, ``HTTPS_PROXY``, and the certificate environment variables (``SSL_CERT_FILE``, ``REQUESTS_CA_BUNDLE``, ``NODE_EXTRA_CA_CERTS``, etc.) on the command automatically, and exits with the command's exit code.

.. code-block::

    mitm                                      # Start proxy on default port.
    mitm -p 9999                              # Start proxy on port 9999.
    mitm -- curl https://example.com          # Capture curl's traffic.
    mitm -- python my_script.py               # Capture a script's traffic.
    mitm -v -- python my_script.py            # Capture a script's traffic, with headers and bodies.
    mitm --json -o traffic.jsonl -- npm ci    # Capture npm's traffic as JSON.

Questions & Answers
--------------------

**How does this project differ from** ``mitmproxy`` **?**

Purpose, implementation, and customization style. The purpose of mitm is to be a light-weight customizable man-in-the-middle proxy intended for larger projects. ``mitmproxy`` (with its beautiful CLI) seems to be more for interactive request and response tampering and capturing. While it does support everything ``mitm`` does plus more, it lacks the simplicity that mitm has.

**What protocols are supported out-of-the-box?**

Only HTTP/1.0 and HTTP/1.1 are supported. Any other protocol (FTP, SMTP, etc.) will require a custom implementation. Any protocol that is built on top of HTTP/1.1 (e.g. websockets) should in theory work.
