##########
Quickstart
##########

A customizable man-in-the-middle TCP proxy with out-of-the-box support for HTTP & HTTPS.

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

    from mitm import MITM, protocol, middleware, crypto

    mitm = MITM(
        host="127.0.0.1",
        port=8888,
        protocols=[protocol.HTTP],
        middlewares=[middleware.Log],
        buffer_size=8192,
        timeout=5,
        keep_alive=True,
        ssl_context=crypto.mitm_ssl_default_context(),
    )
    mitm.run()

This will start a proxy on port 8888 that is capable of intercepting all HTTP traffic (with support for `CONNECT`), and log all activity.

Questions & Answers
--------------------

**How does this project differ from** ``mitmproxy`` **?**

Purpose, implementation, and customization style. The purpose of mitm is to be a light-weight customizable man-in-the-middle proxy intended for larger projects. ``mitmproxy`` (with its beautiful CLI) seems to be more for interactive request and response tampering and capturing. While it does support everything ``mitm`` does plus more, it lacks the simplicity that mitm has.

**What protocols are supported out-of-the-box?**

Only HTTP/1.0 and HTTP/1.1 are supported. Any other protocol (FTP, SMTP, etc.) will require a custom implementation. Any protocol that is built on top of HTTP/1.1 (e.g. websockets) should in theory work.
