class BaseError(Exception):
    def error_message(self):
        return None

    def __str__(self):
        em = self.error_message()
        if em is None:
            return type(self).__name__
        return f"{type(self).__name__}: {em}"


class Exceptions(BaseError):
    def __init__(self, msg: str = "", *, cause: Exception | None = None, payload=None):
        self.msg = msg
        self.cause = cause
        self.payload = payload

    def error_message(self):
        return self.msg or None


class Error(Exceptions):
    pass
