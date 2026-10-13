#####
proxy
#####

.. code-block:: python

    from mitm import MITM

.. automodule:: mitm.proxy

-----

.. autoclass:: mitm.proxy.MITM
    
    .. automethod:: mitm.proxy.MITM.__init__
    .. automethod:: mitm.proxy.MITM.start

        The server is started by using `asyncio.start_server <https://docs.python.org/3/library/asyncio-stream.html#asyncio.start_server>`_ function like so:

        .. code-block:: python

            ...
            self.server = await asyncio.start_server(self.accept, host=self.host, port=self.port)
            ...

    .. automethod:: mitm.proxy.MITM.stop
    .. automethod:: mitm.proxy.MITM.run
    .. automethod:: mitm.proxy.MITM.mitm
    .. automethod:: mitm.proxy.MITM.serve_certificate
