"""lufah exceptions"""


class LufahWarning(UserWarning):
    """Base class for lufah warning exceptions"""


class LufahError(Exception):
    """Base class for lufah error exceptions"""


class FahClientGroupDoesNotExist(LufahError):
    """group does not exist"""


class FahClientNotConnected(LufahError):
    """FahClient is not connected"""


class FahClientUnknownCommand(LufahError):
    """Unknown client command"""
