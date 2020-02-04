from .utils import cached_property
from .types import is_link, is_list, validate
from .resource import Resource, is_resolved
from .exceptions import TypeValidationError


def last_part(key, sep='.'):
    parts = key.split(sep)
    return parts[-1]


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
            "resource": {
                "type": "@resources",
                "inverse": "fields"
            },
            "source": {
                "type": "?string",
            },
            "inverse": {'type': '?string'},
            "name": {"type": "string"},
            "can": {
                "type": "union",
                "of": [{
                    "type": "object",
                    "of": "boolean"
                }, {
                    "type": "array",
                    "of": "string"
                }]
            },
            "type": {"type": "type"},
        }

    def __init__(self, *args, **kwargs):
        super(Field, self).__init__(*args, **kwargs)
        type = self.get_option('type')
        self._is_link = is_link(type)
        self._is_list = is_list(type)

    def setup(self):
        if not self._setup:
            # set initial value via parent
            name = self.get_option('name')
            default = self.get_option('default')
            value = self.parent.get_option(name, default)
            self.set_value(value)

    @property
    def parent(self):
        return self.get_option('parent')

    @classmethod
    def make(cls, *args, **kwargs):
        return cls(*args, **kwargs)  # lazy(lambda: cls(*args, **kwargs), cls)()

    def get_value(self, resolve=True, id=False):
        self.setup()
        if resolve and self._is_link:
            link = self._link
            return link.get_id() if id else link
        else:
            return self._value

    def get_space(self):
        space = None
        parent = self.parent
        if parent.get_meta('space') == '.':
            # get root space
            parent_name = parent.get_meta('name')
            while parent_name == 'fields':
                parent = parent.parent
                parent_name = parent.get_meta('name')

            if parent_name == 'server':
                space = parent.root
            elif parent_name == 'resources':
                space = parent.get_option('space')
                if not is_resolved(space):
                    space = parent.space
            elif parent_name == 'spaces':
                space = parent
            elif parent_name == 'types':
                space = parent.server.root
        else:
            # get space from parent resource
            space = parent.space
        return space

    def get_link(self, value):
        if is_resolved(value):
            return value

        return self.get_space().resolve(self.type, value)

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
            link = None

            if is_resolved(value):
                # resource given -> get ID or IDs
                link = value
                value = [v.get_id() for v in value] if self._is_list else link.get_id()

                self._value = value
                self.__dict__["_link"] = link
                if set_inverse and self.inverse:
                    self.set_inverse(link)
            else:
                # id or ids given
                self._value = value
                link = self.__dict__['_link'] = self.get_link(value)

            if link and set_inverse and self.inverse:
                self.set_inverse(link)
        else:
            # simple assignment without links
            self._value = value

        self._setup = True

    def set_inverse(self, value):
        parent = self.parent
        if not parent:
            return

        if not isinstance(value, list):
            value = [value]

        inverse = self.inverse

        for v in value:
            inverse_field = v.get_field(inverse)
            if inverse_field._is_list:
                inverse_field.add_value(parent, set_inverse=False)
            else:
                inverse_field.set_value(parent, set_inverse=False)

    def add_value(self, new_value, set_inverse=True, index=None):
        if self._is_list:
            self.setup()

            value = self._value
            link = None

            if value is None:
                value = self._value = []

            if not isinstance(new_value, list):
                new_value = [new_value]

            ids = None
            link = None
            resolved = None

            if self._is_link:
                resolved = is_resolved(new_value)
                link = self._link
                ids = set([v.get_id() if hasattr(v, 'get_id') else v for v in link])

            news = []
            for v in new_value:
                if self._is_link:
                    # check ids before adding
                    if resolved:
                        id = v.get_id()
                        if id not in ids:
                            ids.add(id)
                            news.append(v)
                            value.append(id)
                            link.append(v)
                    else:
                        if v not in ids:
                            ids.add(v)
                            value.append(v)
                            news.append(v)
                else:
                    # add directly
                    value.append(v)

            if self._is_link and not resolved:
                # news has ids
                news = self.get_link(news)
                link.extend(news)

            if set_inverse and self.inverse and news:
                self.set_inverse(news)
        else:
            # cannot add on a non-list
            # TODO: support this for strings, objects, numbers
            raise NotImplementedError()

    @cached_property
    def _link(self):
        return self.get_link(self._value)
