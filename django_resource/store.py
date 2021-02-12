from .utils import cached_property, get
from .query import Query


def get_store_class(engine):
    if engine == 'django':
        from .django.store import DjangoStore
        return DjangoStore
    elif engine == 'api':
        raise NotImplementedError()
    elif engine == 'resource':
        raise NotImplementedError()
    else:
        raise NotImplementedError()


class Store:
    def __init__(self, resource):
        self.server = self.resource = self.space = None
        if resource.__class__.__name__ == 'Space':
            self.space = resource
        elif resource.__class__.__name__ == 'Resource':
            self.resource = resource
        elif resource.__class__.__name__ == 'Server':
            self.server = resource

    def get_space(self):
        if self.resource:
            return self.resource.space
        elif self.space:
            return self.space
        else:
            return None

    def get_server(self):
        if self.resource:
            return self.resource.space.server
        if self.space:
            return self.space.server
        return self.server

    def get_executor(self):
        raise NotImplementedError()

    def get_resolver(self):
        raise NotImplementedError()

    @cached_property
    def executor(self):
        return self.get_executor()

    @cached_property
    def resolver(self):
        return self.get_resolver()

    @property
    def query(self):
        return self.get_query()

    def get_query(self, querystring=None):
        initial = {}
        if self.space:
            initial['space'] = self.space.name
        elif self.resource:
            initial["resource"] = self.resource.name
            initial["space"] = self.resource.space.name

        executor = self.executor
        if querystring:
            return Query.from_querystring(
                querystring,
                state=initial,
                executor=executor
            )
        else:
            return Query(
                state=initial,
                executor=executor
            )
