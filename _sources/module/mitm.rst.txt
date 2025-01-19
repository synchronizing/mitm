####
mitm
####

.. code-block:: python

    from mitm import MITM

.. automodule:: mitm.mitm

-----

.. autoclass:: mitm.mitm.MITM
    
    .. automethod:: mitm.mitm.MITM.__init__
    .. automethod:: mitm.mitm.MITM.entry

        The server is started by using `asyncio.start_server <https://docs.python.org/3/library/asyncio-stream.html#asyncio.start_server>`_ function like so:

        .. code-block:: python

            ...
            server = await asyncio.start_server(
                lambda reader, writer: self.mitm(
                    Connection(
                        client=Host(reader=reader, writer=writer),
                        server=Host(),
                    )
                ),
                host=self.host,
                port=self.port,
            )
            ...

    .. automethod:: mitm.mitm.MITM.mitm
