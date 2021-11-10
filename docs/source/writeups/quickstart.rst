##########
Quickstart
##########

``mitm`` is a customizable man-in-the-middle proxy with support for HTTP and HTTPS capturing.

Installing
----------

I'm currently working on getting PyPi's ``mitm`` page. As of right now, you can install via GitHub:

.. code-block::
    
    pip install http://github.com/synchronizing/mitm

Note that OpenSSL 1.1.1 or greater is required.

Using
-----

By itself `mitm` is not very special. You can boot it up and view debug messages quite easily:

.. code-block:: python

    from mitm import MITM, Config
    import logging

    config = Config(log_level=logging.DEBUG)
    MITM.start(config)

``mitm`` becomes more useful when you either use the middleware system, or inherit and extend :py:class:`mitm.mitm.MITM`. Check out the `customizing guide </writeups/customizing.html>`_ for more information.

Questions & Answers
--------------------

**How does this project differ from** ``mitmproxy`` **?**

Purpose, implementation, and customization style. The purpose of mitm is to be a light-weight customizable man-in-the-middle proxy intended for larger projects. ``mitmproxy`` (with its beautiful CLI) seems to be more for interactive request and response tampering and capturing. While it does support everything ``mitm`` does plus more, it lacks the simplicity that mitm has.

**What protocols are supported out-of-the-box?**

Only HTTP/1.0 and HTTP/1.1 are supported. Any other protocol (FTP, SMTP, etc.) will require a custom implementation. Any protocol that is built on top of HTTP/1.1 (e.g. websockets) should in theory work.
