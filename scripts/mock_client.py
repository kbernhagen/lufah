#!/usr/bin/env python3
"""Mock FahClient Server"""

__version__ = "0.1.0"

import asyncio
import json
import logging
import os
import re
import socket
import sys

import websockets
from argh import arg, dispatch_command  # pylint: disable=import-error

from lufah.updatable import Updatable
from lufah.util import load_json_objects_from_file


class CustomFormatter(logging.Formatter):
    """Custom logging formatter with different formats by log level."""

    FORMATS = {
        logging.DEBUG: "%(levelname)s: %(message)s",
        logging.INFO: "%(message)s",
        logging.WARNING: "%(levelname)s: %(message)s",
        logging.ERROR: "%(levelname)s: %(message)s",
        logging.CRITICAL: "%(levelname)s: %(message)s",
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno, self._fmt)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


# Pre-setup logging
logger = logging.getLogger("mockclient")
simple_log_handler = logging.StreamHandler()
simple_log_handler.setFormatter(CustomFormatter())
simple_log_handler.setLevel(logging.DEBUG)  # don't filter out anything
# logger.addHandler(simple_log_handler)  # done later as appropriate


class MockServer:  # pylint: disable=R0902
    """Mock FahClient Server"""

    def __init__(
        self, name: str = "", port: int = 8765, delay: int = 1, data_file: str = ""
    ):
        """Initialize the mock client."""
        self._name = name
        self._port = port
        # clamp delay after "ping" update to 0..20 secs
        self._delay = max(min(delay, 20), 0)
        self._data_file = data_file
        self._background_tasks = set()
        self._clients = set()  # Set of connected WebSocket clients
        self._state = Updatable()
        self._updates: asyncio.Queue = None  # must be created inside async loop
        self._shutdown_event: asyncio.Event = None  # must be created inside async loop

    async def _initialize_state(self):
        """Initialize state and updates from data_file."""
        if len(self._state):
            return  # already loaded
        self._updates = asyncio.Queue()
        hostname = socket.gethostname()
        objects = load_json_objects_from_file(self._data_file)
        if objects:
            logger.info(
                "Loaded initial state and updates from %s (%s objects)",
                self._data_file,
                len(objects),
            )
            self._state.update(objects[0])
            self._state.do_update(["info", "hostname", hostname])
            self._state.do_update(["info", "mach_name", self._name])
            for update in objects[1:]:
                await self._updates.put(update)
        else:
            logger.error("No JSON objects in data file %s", self._data_file)
            logger.warning(
                "Continuing with no JSON objects for client state and updates"
            )

    async def _apply_updates_and_broadcast(self):
        """
        Merge available updates and broadcast to all connected clients.
        If update was "ping", sleep delay seconds.
        If no updates available, send "ping" after a fixed timeout.
        """
        await asyncio.sleep(10)  # additional start delay for debugging
        while True:
            # Fetch an update with timeout
            try:
                update = await asyncio.wait_for(self._updates.get(), timeout=20)
            except asyncio.TimeoutError:
                # "ping" if no updates within timeout
                websockets.broadcast(self._clients, '"ping"')
                logger.info("Broadcasted %s", '"ping"')
                continue

            # Apply update
            self._state.do_update(update)

            # Broadcast update to all connected clients
            if self._clients:
                message = json.dumps(update)
                websockets.broadcast(self._clients, message)
                logger.info(
                    "Broadcasted update to %s client%s: %s",
                    len(self._clients),
                    "s" if len(self._clients) != 1 else "",
                    update,
                )
            else:
                logger.info("No clients to broadcast update: %s", update)

            # Arbitrarily delay if data_file update was "ping"
            if update == "ping":
                await asyncio.sleep(self._delay)

    async def _receive_requests(
        self, websocket: websockets.WebSocketServerProtocol, remote_addr: str
    ):
        """Receive and log incoming JSON requests."""
        async for message in websocket:
            try:
                if not message:
                    logger.debug("Ignoring empty message from %s", remote_addr)
                    continue
                data = json.loads(message)
                logger.info("Received from %s: %s", remote_addr, message)
                # Note: shutdown is NOT a standard v8 fahclient command
                if isinstance(data, dict):
                    cmd = data.get("cmd")
                    if cmd == "shutdown":
                        self.shutdown()
            except json.JSONDecodeError:
                logger.warning(
                    "Received non-JSON message from %s: %s", remote_addr, message
                )

    async def _new_client_handler(
        self, websocket: websockets.WebSocketServerProtocol, _path: str
    ):
        """Handle new client connection."""
        # ignore path, assumed to be "/api/websocket"
        remote_addr = websocket.remote_address
        logger.info("Client connected: %s", remote_addr)
        self._clients.add(websocket)
        try:
            # Send current server state to the client
            await websocket.send(json.dumps(self._state))

            # Run request receiver
            await self._receive_requests(websocket, remote_addr)
        finally:
            self._clients.remove(websocket)
            logger.info("Connection removed: %s", remote_addr)

    async def start(self):
        """Start the WebSocket server. Blocks until shutdown or interrupt."""
        await self._initialize_state()
        self._shutdown_event = asyncio.Event()
        try:
            async with websockets.serve(
                self._new_client_handler, "0.0.0.0", self._port
            ):
                logger.info("Serving '%s' on ws://0.0.0.0:%s", self._name, self._port)
                task = asyncio.create_task(self._apply_updates_and_broadcast())
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.remove)
                await self._shutdown_event.wait()
        finally:
            self.shutdown()

    def shutdown(self):
        """Shutdown the server gracefully."""
        if self._shutdown_event is None or self._shutdown_event.is_set():
            return
        logger.info("Shutting down...")
        for task in self._background_tasks:
            task.cancel()
        self._shutdown_event.set()


@arg("--version", action="version", version=__version__, help="")
@arg("-v", "--verbose", help="")
@arg("-d", "--debug", help="")
@arg("--port", help="Port number for incoming connections (1024-65535)")
@arg("--delay", help='Seconds delay after reading "ping" update (0-20)')
@arg(
    "--name",
    help="Machine name or IP address",
    default=socket.gethostname() + "Mock",
)
@arg("--data-file", help="Data file containing JSON dict and array updates")
def serve(  # pylint: disable=too-many-arguments,too-many-branches
    version=False,  # pylint: disable=unused-argument
    verbose=False,
    debug=False,
    port: int = 8765,
    delay: int = 1,
    name: str = None,
    data_file="data/lufahwatch3.jsonl",
):
    """Setup and start the mock client websocket server."""

    # Set logging based on flags
    if debug and verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logger.addHandler(simple_log_handler)

    if debug:
        logger.setLevel(logging.DEBUG)
    elif verbose:
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.WARNING)

    # validate port
    if not 1024 <= port <= 65535:
        logger.error("Port must be a valid non-privileged port number (1024-65535).")
        raise SystemExit(1)

    # validate name (machine-name)
    if not re.match(r"^[^\s\\<>;&'\"]{1,64}$", name):
        name = name.strip()
        if not name:
            name = "MockClient"
        else:
            name = re.sub(r"[\s\\<>;&'\"]", "-", name)
            name = name[:63]
        logger.warning("Invalid name. Using %s.", repr(name))

    server = MockServer(name=name, port=port, delay=delay, data_file=data_file)
    asyncio.run(server.start())


def main():
    """main entrypoint"""
    try:
        dispatch_command(serve)
    except KeyboardInterrupt:
        pass
    except BrokenPipeError:
        # This is common if piping to 'head' or 'more'
        # Python flushes standard streams on exit; redirect remaining output
        # to devnull to avoid another BrokenPipeError at shutdown
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    except Exception as e:  # pylint: disable=W0718
        logger.error("%s", e)


if __name__ == "__main__":
    main()
