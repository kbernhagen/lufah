"""top command"""

from __future__ import annotations

import argparse
import asyncio
import logging

try:
    import curses

    HAVE_CURSES = True
except ImportError:
    # probably Windows without windows-curses
    HAVE_CURSES = False

import datetime as dt

from lufah.commands.core.units import units_table_lines
from lufah.fahclient import FahClient
from lufah.logger import logger


class Topper:  # pylint: disable=R0903
    """units table top"""

    def __init__(self, clients: list[FahClient]) -> None:
        self._clients = clients
        self._screen = None
        self._draw_event: asyncio.Event = None
        self._background_tasks = set()

    def _background_task_done(self, task):
        self._background_tasks.remove(task)
        self._draw_event.set()

    async def _on_message(self, _client, _message):
        if self._draw_event is not None:
            self._draw_event.set()

    def _draw(self, screen):
        """Draw if draw_event is set."""
        if not self._draw_event.is_set():
            return
        self._draw_event.clear()
        try:
            curses.resize_term(0, 0)  # for Windows
        except:  # noqa: E722
            pass
        screen.clear()
        maxy, maxx = self._screen.getmaxyx()
        maxx -= 1
        maxy -= 1
        lines = units_table_lines(self._clients)
        if lines[0].startswith("---"):
            del lines[0]  # first line is decor
        # draw clipped timestamp in lower right
        timestamp = str(dt.datetime.now().replace(microsecond=0))[:maxx]
        screen.addstr(maxy, maxx - len(timestamp), timestamp)
        # draw units table, clipped to terminal screen
        i = 0
        for line in lines:
            if i > maxy:
                break
            screen.addstr(i, 0, line[:maxx])
            i += 1
        # park cursor in case of logger messages
        if i < maxy:
            screen.move(i, 0)
        screen.refresh()

    async def _run(self):
        "Show table of all units by machine name and group."
        self._draw_event = asyncio.Event()
        clients = self._clients
        for client in clients:
            client.register_callback(self._on_message)
            task = asyncio.create_task(client.connect())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_task_done)
        self._draw_event.set()
        while True:
            self._draw(self._screen)
            char = self._screen.getch()
            if char == curses.KEY_RESIZE:
                # Windows does not get key
                self._draw_event.set()
            elif char == curses.ERR:
                await asyncio.sleep(0.25)  # vital that we yield to event loop
            else:
                try:
                    if chr(char) == " ":
                        self._draw_event.set()
                    elif chr(char) == "q":
                        break
                except:  # noqa: E722
                    pass

    async def run(self):
        level = logger.getEffectiveLevel()
        self._screen = curses.initscr()
        try:
            curses.curs_set(0)
            curses.noecho()
            self._screen.nodelay(True)
            logger.setLevel(logging.CRITICAL)
            await self._run()
        finally:
            curses.echo()
            curses.curs_set(1)
            curses.endwin()
            logger.setLevel(level)


async def do_top(args: argparse.Namespace):
    """
    Show top-like updating units table. Type 'q' to quit, space to force redraw.
    """
    await Topper(args.clients).run()
