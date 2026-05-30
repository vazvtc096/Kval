from Kval.PyModules.PythonBridge import export


@export
def add(a: int, b: int) -> int:
    return a + b


def hidden():
    return 999


__kval_exports__ = ["add"]
