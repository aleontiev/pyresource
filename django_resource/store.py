from .utils import cached_property, get
from .query import Query


class Store:
    def __init__(self, resource):
        self._server = self._resource = self._space = None
        if resource.__class__.__name__ == 'Space':
            self._space = resource
        elif resource.__class__.__name__ == 'Resource':
            self._resource = resource
        elif resource.__class__.__name__ == 'Server':
            self._server = resource
        else:
            raise ValueError(f'{resource} is not a valid resource')

    @cached_property
    def space(self):
        if self._resource:
            return self._resource.space
        elif self._space:
            return self._space
        return None

    @cached_property
    def server(self):
        if self._resource:
            return self._resource.space.server
        if self._space:
            return self._space.server
        return self._server

    @cached_property
    def resource(self):
        return self._resource

    @property
    def query(self):
        return self.get_query()

    def get_query(self, querystring=None):
        initial = {}
        if self._space:
            initial['space'] = self.space.name
        elif self._resource:
            initial["resource"] = self.resource.name
            initial["space"] = self.space.name

        server = self.server
        if querystring:
            return Query.from_querystring(
                querystring,
                state=initial,
                server=server
            )
        else:
            return Query(
                state=initial,
                server=server
            )
