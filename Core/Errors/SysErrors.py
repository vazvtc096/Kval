from .BaseErrors import Exceptions


class SysError(Exceptions):
    pass


class SysIOError(SysError):
    pass


class SysMemoryError(SysError):
    pass