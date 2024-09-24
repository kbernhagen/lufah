"""shared logger"""

__all__ = ["logger", "simple_log_handler"]

import logging


# Custom logging formatter
class CustomFormatter(logging.Formatter):
    """Custom logging formatter with different formats by log level."""

    FORMATS = {
        logging.DEBUG: "%(levelname)s:%(filename)s:%(lineno)s: %(message)s",
        logging.INFO: "%(message)s",
        logging.WARNING: "Warning: %(message)s",
        logging.ERROR: "Error: %(message)s",
        logging.CRITICAL: "%(levelname)s: %(message)s",
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno, self._fmt)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


# Pre-setup logging
logger = logging.getLogger("lufah")
simple_log_handler = logging.StreamHandler()
simple_log_handler.setFormatter(CustomFormatter())
simple_log_handler.setLevel(logging.DEBUG)  # don't filter out anything
# logger.addHandler(simple_log_handler)  # done later as appropriate
