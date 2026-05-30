from .BaseErrors import Error, Exceptions


class RunTimeError(Exceptions):
    pass


class TypeRunTimeError(RunTimeError):
    pass


class ValueRunTimeError(RunTimeError):
    pass


class NameRunTimeError(RunTimeError):
    pass


class TypeError(TypeRunTimeError):
    pass


class ValueError(ValueRunTimeError):
    pass


class NameError(NameRunTimeError):
    pass


class IndexError(ValueRunTimeError):
    pass


class KeyError(ValueRunTimeError):
    pass


class PermissionError(RunTimeError):
    pass


class ZeroDivisionError(RunTimeError):
    pass


class ImportError(RunTimeError):
    pass


class AttributeError(NameRunTimeError, Error):
    def __init__(self, obj, name: str):
        self.obj = obj
        self.name = name

    def error_message(self):
        return f"'{self.obj!r}' has no attribute '{self.name}'"
