from django.db import transaction
from contextlib import contextmanager


@contextmanager
def maybe_atomic(atomic):
    if atomic:
        with transaction.atomic():
            yield
    else:
        yield


class maybe_capture_queries:
    def __init__(self, capture=True, connection=None):
        self.queries = []
        self._capture = capture
        if not capture:
            return

        if connection is None:
            from django import db
            connection = db.connection
        self._connection = connection
        self._initial = 0

    def __enter__(self):
        if not self._capture:
            return self

        self._force_debug_cursor = self._connection.force_debug_cursor
        self._connection.force_debug_cursor = True
        self._initial = len(self._connection.queries)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if not self._capture:
            return

        self._connection.force_debug_cursor = self._force_debug_cursor
        if exc_type is not None:
            return

        self.queries = self._connection.queries[self._initial:]
