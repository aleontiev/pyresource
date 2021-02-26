from django.db import transaction
from contextlib import contextmanager


@contextmanager
def maybe_atomic(atomic):
    if atomic:
        with transaction.atomic():
            yield
    else:
        yield
