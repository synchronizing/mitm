"""
Command line interface for mitm.
"""

import logging

import click

from .config import Config
from .mitm import MITM

config = Config()


@click.group()
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="Run mitm with debug prints.",
)
def main(debug: bool):
    if debug:
        config.log_level = logging.DEBUG


@main.command("start", help="Start the mitm server.")
@click.option(
    "--host",
    "-h",
    default=config.host,
    help=f"Host to run mitm in. Defaults to {config.host}.",
)
@click.option(
    "--port",
    "-p",
    default=config.port,
    help=f"Port to run mitm in. Defaults to {config.port}.",
)
def start(host, port):
    config.host = host
    config.port = port

    MITM.start(config)
