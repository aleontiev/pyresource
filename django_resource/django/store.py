from django_resource.store import Store
from .executor import DjangoExecutor
from .resolver import DjangoSchemaResolver


class DjangoStore(Store):
    def get_executor(self):
        return DjangoExecutor(self)

    def get_resolver(self):
        return DjangoSchemaResolver(self)
