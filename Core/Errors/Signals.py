from ..Types.Base import Object

class Signal(Exception): pass

class ReturnSignal(Signal):
    def __init__(self, value: Object):
        self.value = value
    def __str__(self):
        return f'Signal: {self.value}'


class BreakSignal(Signal):
    """由 break 语句抛出，由循环体捕获。"""


class ContinueSignal(Signal):
    """由 continue 语句抛出，由循环体捕获。"""