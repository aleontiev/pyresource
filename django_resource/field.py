from .utils import cached_property
from .types import is_link, is_list, validate
from .resource import Resource, is_resolved
from .exceptions import TypeValidationError


class Field(Resource):
    class Schema:
        id = "fields"
        name = "fields"
        space = "."
        description = "Description of fields"
        fields = {
            "id": {
                "type": "string",
                "primary": True,
            },
            "resource": {"type": "@resource", "inverse": "fields"},
            "inverse": {'type': '?string'},
            "name": {"type": "string"},
            "type": {"type": "type"},
        }

    def __init__(self, *args, **kwargs):
        super(Field, self).__init__(*args, **kwargs)
        self._setup = False
        self.setup()

    def setup(self):
        if not self._setup:
            type = self.get_option('type')

            self._is_link = is_link(type)
            self._is_list = is_list(type)

            resource = self.get_option('resource')
            name = self.get_option('name')
            default = self.get_option('default')
            value = resource.get_option(name, default)
            print(resource, 'set', name, 'to', value)
            self.set_value(value)
            self._setup = True

    @classmethod
    def make(cls, *args, **kwargs):
        return cls(*args, **kwargs)  # lazy(lambda: cls(*args, **kwargs), cls)()

    def get_value(self, resolve=True, id=False):
        if resolve and self._is_link:
            link = self._link
            return link.get_id() if id else link
        else:
            return self._value

    def get_link(self, value):
        if is_resolved(value):
            return value

        return self.get_option('resource').space.resolve(self.type, value)

    def validate(self, type, value):
        try:
            return validate(type, value)
        except TypeValidationError as e:
            print(f"{self.name} validation failed: {e}")
            raise

    def set_value(self, value, set_inverse=True):
        type = self.get_option('type')
        self.validate(type, value)
        if self._is_link:
            if is_resolved(value):
                # resource given -> get ID or IDs
                link = value
                value = [v.get_id() for v in value] if self._is_list else link.get_id()

                self._value = value
                self.__dict__["_link"] = link
                if set_inverse and self.inverse:
                    self.set_inverse(link)
            else:
                # id or ids given -> resolve links later
                self._value = value
                self.__dict__.pop("_link", None)
        else:
            # simple assignment without links
            self._value = value

    def set_inverse(self, value):
        resource = self.get_option('resource')
        if not resource:
            return

        if not isinstance(value, list):
            value = [value]

        try:
            inverse = resource.inverse
        except Exception:
            inverse = self.inverse
        import pdb
        pdb.set_trace()

        for v in value:
            inverse_field = v.get_field(inverse)
            if inverse_field._is_list:
                inverse_field.add_value(resource, set_inverse=False)
            else:
                inverse_field.set_value(resource, set_inverse=False)

    def add_value(self, new_value, set_inverse=True, index=None):
        if self._is_list:
            value = self._value
            link = None

            if value is None:
                value = self._value = []

            if not isinstance(new_value, list):
                new_value = [new_value]

            ids = None
            link = None
            if self._is_link:
                link = self._link
                ids = set([v.get_id() if hasattr(v, 'get_id') else v for v in link])

            news = []
            for v in new_value:
                if self._is_link:
                    # check ids before adding
                    id = v.get_id()
                    if id not in ids:
                        news.append(v)
                        value.append(id)
                        link.append(v)
                else:
                    # add directly
                    value.append(v)

            if set_inverse and self.inverse and news:
                self.set_inverse(news)
        else:
            # cannot add on a non-list
            # TODO: support this for strings, objects, numbers
            raise NotImplementedError()

    @cached_property
    def _link(self):
        return self.get_link(self._value)
