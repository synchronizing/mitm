"""
Configuration settings for mitm.
"""

from typing import List
import logging
import pathlib
import asyncio

import appdirs

from . import __author__, __project__, crypto
from .middleware import Middleware

logger = logging.getLogger(__package__)

# System specific data directory.
data_directory = pathlib.Path(appdirs.user_data_dir(__project__, __author__))


class Config:
    def __init__(
        self,
        loop: asyncio.BaseEventLoop = asyncio.get_event_loop(),
        host: str = "127.0.0.1",
        port: int = 8888,
        buffer_size: int = 8192,
        rsa_key: pathlib.Path = data_directory / "mitm.key",
        rsa_cert: pathlib.Path = data_directory / "mitm.crt",
        rsa_generate: bool = True,
        middlewares: List[Middleware] = [],
        log_level: int = logging.INFO,
    ):
        """
        Configuration settings for the man-in-the-middle server.

        Note:
            The RSA key and certificate are stored in the operating system data
            directory as specified by the `appdirs <https://github.com/ActiveState/appdirs>`_
            module.

        Args:
            loop: The event loop to use. Defaults to the current event loop.
            host: The host to bind to. Defaults to ``127.0.0.1``.
            port: The port to bind to. Defaults to ``8888``.
            buffer_size: The size of the buffer to use for reading. Defaults to ``2048``.
            rsa_key: Path to the RSA key to use. Defaults to the OS' data directory.
            rsa_cert: Path to the RSA cert to use. Defaults to the OS' data directory.
            rsa_generate: Whether to generate a new RSA key and cert. Defaults to ``True``.
            middlewares: Middlewares to use. Defaults empty list.
            log_level: The log level to use. Defaults to ``logging.INFO``.
        """

        # Asyncio settings.
        self.loop = loop

        # Server settings.
        self.host = host
        self.port = port
        self.buffer_size = buffer_size

        # RSA Information
        self.rsa_key = rsa_key
        self.rsa_cert = rsa_cert

        if rsa_generate:
            rsa_key.parent.mkdir(parents=True, exist_ok=True)
            rsa_cert.parent.mkdir(parents=True, exist_ok=True)

            key, crt = crypto.new_pair()

            with rsa_key.open("wb") as file:
                file.write(key)

            with rsa_cert.open("wb") as file:
                file.write(crt)

        # Log Settings
        self.log_level = log_level

        # Middleware
        self.middlewares = middlewares

    def add_middleware(self, middleware: Middleware):
        """
        Add a middleware to the configuration.

        Args:
            middleware: The middleware to add.
        """
        self.middlewares.append(middleware)

    def remove_middleware(self, middleware: Middleware):
        """
        Remove a middleware from the configuration.

        Args:
            middleware: The middleware to remove.
        """
        if middleware in self.middlewares:
            self.middlewares.remove(middleware)
        else:
            raise KeyError(f"Middleware {middleware.__name__} not found.")

    @property
    def log_level(self):
        return logger.level

    @log_level.setter
    def log_level(self, value):
        logger.setLevel(value)
