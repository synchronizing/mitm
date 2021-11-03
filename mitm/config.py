"""
Configuration module.
"""

from typing import Dict
import logging
import pathlib
import asyncio

import appdirs

from . import __author__, __project__, crypto

logger = logging.getLogger(__package__)

# System specific data directory.
data_directory = pathlib.Path(appdirs.user_data_dir(__project__, __author__))


class Config:
    def __init__(
        self,
        loop: asyncio.BaseEventLoop = asyncio.get_event_loop(),
        host: str = "127.0.0.1",
        port: int = 8888,
        buffer_size: int = 2048,
        rsa_key: pathlib.Path = data_directory / "mitm.key",
        rsa_cert: pathlib.Path = data_directory / "mitm.crt",
        rsa_generate: bool = True,
        middlewares: Dict["str", "middleware.Middleware"] = {},
        log_level: int = logging.INFO,
    ) -> None:
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

    def add_middleware(self, name: str, middleware: "middleware.Middleware"):
        self.middlewares[name] = middleware

    def remove_middleware(self, name: str):
        if name in self.middlewares:
            del self.middlewares[name]
        else:
            raise KeyError(f"Middleware {name} not found.")

    @property
    def log_level(self):
        return logger.level

    @log_level.setter
    def log_level(self, value):
        logger.setLevel(value)
