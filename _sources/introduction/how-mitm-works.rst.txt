##############
How mitm works
##############

A high-level overview on how a man-in-the-middle proxy works.

----

`mitm` is a TCP proxy server that is capable of intercepting requests and responses going through it.

To understand how an mitm proxy works let's take a look at a simple example using the HTTP protocol. Let's familiarize ourselves with a raw HTTP communication, how a normal proxy functions, and finally how an MITM proxy works.

----

HTTP & HTTPS 
------------

For the sake of example, imagine a client is trying to reach `example.com`:

.. code-block:: python

    import requests
    requests.get("http://example.com")

Whether the client is trying to reach the domain via the `requests` module or their browser, both methods must generate a valid HTTP request to send to the server. In the case of the above, `requests` would generate the following HTTP request:

.. code-block::

    GET http://example.com/ HTTP/1.1
    Host: example.com
    User-Agent: python-requests/2.26.0
    Accept-Encoding: gzip, deflate
    Accept: */*
    Connection: keep-alive

This HTTP request is sent through hundreds of miles of wires until it reaches the server, which interprets the message, and replies back with the requested page:

.. code-block::

    HTTP/1.1 200 OK
    Content-Encoding: gzip
    Accept-Ranges: bytes
    Age: 111818
    Cache-Control: max-age=604800
    Content-Type: text/html; charset=UTF-8
    Date: Fri, 05 Nov 2021 18:49:47 GMT
    Etag: "3147526947"
    Expires: Fri, 12 Nov 2021 18:49:47 GMT
    Last-Modified: Thu, 17 Oct 2019 07:18:26 GMT
    Server: ECS (agb/5295)
    Vary: Accept-Encoding
    X-Cache: HIT
    Content-Length: 648
    [data]

The server, like the client, strictly follows the RFCs that define the `HTTP <https://en.wikipedia.org/wiki/Hypertext_Transfer_Protocol>`_ protocol. In some cases, however, the client might want to create a more secure connection with the server. We know of this as HTTPS, which stands for HTTP secure. To do this, a client would connect to the server with the `https` prefix:

.. code-block:: python

    import requests
    requests.get("https://example.com")

In this case, the clients initial request will be

.. code-block::
    
    CONNECT example.com:443 HTTP/1.0

Which indicates that the client is ready to begin a secure connection with the server. When the server receives this message it replies back to the client

.. code-block::

    HTTP/1.1 200 OK

And the client begins what is called the "TLS/SSL handshake," which you can read more about it `here <https://www.cloudflare.com/learning/ssl/what-happens-in-a-tls-handshake/>`_. During this handshake the server and the client create a secure tunnel that they can communicate without fear of someone being able to see their communication.

All of the above is important to have a general understanding of to comprehend how proxies work.

----

Proxies
-------

A proxy works by sitting between the client and destination server and is typically used to concel the IP address of a client. A normal proxy would be used either by setting its settings in the browsers' configuration, or via the `proxies` parameter in requests:

.. code-block:: python

    import requests

    proxies = {"http": "http://127.0.0.1:8888", "https": "http://127.0.0.1:8888"}
    requests.get("http://example.com", proxies=proxies)

In this case `requests` will generate the same HTTP request we saw above, but instead of sending it to the destination server - `example.com` - it will send it to the proxy. 

.. code-block::

    GET http://example.com/ HTTP/1.1
    Host: example.com
    User-Agent: python-requests/2.26.0
    Accept-Encoding: gzip, deflate
    Accept: */*
    Connection: keep-alive

The proxy, once it receives the HTTP request, interprets *where* the client is trying to go via either the first line of the request, or the ``Host`` header. It then opens a connection with the destination server on behalf of the client, and allows the client and the server to communicate between each other through *it*. In other words, a proxy is a 'man in the middle' whose job is primairly concentrated on conceling the IP address of the client. 

When a client utilises HTTPS (``https://``) the initial request goes to the proxy, and subsequently the proxy connects the client and server. The difference here, however, is that after the client and server are connected they perform the TLS/SSL handshake and begin a secure connection. This connection is now encrypted and the client and server can communicate freely without fear of being intercepted.

----

Man-in-the-middle
-----------------

`mitm`, therefore, is a proxy that purposely intercepts the requests and responses going through it. When a client connection is a standard HTTP connection the `mitm` server doesn't have to do anything special. It creates a connection to the destination server on behalf of the client and listens to the messages between both. The issue is when a client is trying to connect to the server via HTTPS:

.. code-block:: python

    import requests

    proxies = {"http": "http://127.0.0.1:8888", "https": "http://127.0.0.1:8888"}
    requests.get("https://example.com", proxies=proxies)

When this happens, and the client sends a

.. code-block:: python
    
    CONNECT example.com:443 HTTP/1.0

What `mitm` does is *acts* like the destination server by responding back to the client

.. code-block::

    HTTP/1.1 200 OK

and then performs the TLS/SSL handshake on behalf of the destination server. Once `mitm` and the client are connected it then opens a connection with the destination server and relays their communication back-and-forth, sitting in the middle and listening. Note, however, that since `mitm` generates its own TLS/SSL certificates a client will not trust it unless one either adds the generated certificate to their keychain (**not recommended**) or one uses a special flag in `requests`:

.. code-block:: python

    import requests

    proxies = {"http": "http://127.0.0.1:8888", "https": "http://127.0.0.1:8888"}
    requests.get("https://example.com", proxies=proxies, verify=False)

... and that's really it!
