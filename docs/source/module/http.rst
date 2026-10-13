####
http
####

.. code-block:: python

    from mitm import http

.. automodule:: mitm.http

-----

.. autoclass:: mitm.http.Message
    :members:

.. autoclass:: mitm.http.Exchange

.. autoclass:: mitm.http.Parser
    :members: feed, close

.. autoclass:: mitm.http.Session
    :members: client, server, close, url

.. autofunction:: mitm.http.parse_head

.. autofunction:: mitm.http.split_authority

.. autofunction:: mitm.http.decode
