class _Unsupport:
    pass


unsupported = _Unsupport()


class KvalPtr:
    """指针语义：通过 getter/setter 绑定到某变量槽位（取址 `&x` 产生，解引用读写）。"""

    __slots__ = ("_get", "_set")

    def __init__(self, get_fn, set_fn):
        self._get = get_fn
        self._set = set_fn

    def get(self):
        return self._get()

    def set(self, v):
        return self._set(v)


class Unbound:
    __slots__ = ("name",)

    def __init__(self, name: str):
        self.name = name

    def __repr__(self):
        return f"Unbound({self.name!r})"


skip_unbound_errors: bool = False


def kval_truthy(v) -> bool:
    """与条件语句一致的「真」判定：int 非 0、string 非空、Unbound/None 为假。"""
    if isinstance(v, int):
        return v != 0
    if isinstance(v, str):
        return len(v) > 0
    if v is None:
        return False
    if isinstance(v, Unbound):
        return False
    return bool(v)


def is_truthy(v) -> bool:
    if v is None or v is False:
        return False
    if isinstance(v, Unbound):
        return False
    if isinstance(v, int) and v == 0:
        return False
    return True
