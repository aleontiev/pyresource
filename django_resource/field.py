from django.utils.functional import lazy, cached_property
from .types import is_link, is_list, validate
from .resource import Resource, is_resolved


class Field(Resource):
    class Schema:
        name = "fields"
        space = "."
        description = "Description of fields"
        fields = {
            "id": {
                "type": "string",
                "default": {"format": "{{.resource.id}}.{{.name}}"},
                "primary": True,
            },
            "resource": {"type": "@resource", "inverse": "fields"},
            "name": {"type": "string"},
            "type": {"type": "type"},
        }

    def __init__(self, *args, **kwargs):
        super(Field, self).__init__(*args, **kwargs)

        self.is_link = is_link(self.type)
        self.is_list = is_list(self.type)
        self.set_value(self.resource.get_option(self.name, self.default))

    @classmethod
    def make(cls, *args, **kwargs):
        return lazy(lambda: cls(*args, **kwargs), cls)

    def get_value(self, resolve=True, id=False):
        if resolve and self.is_link:
            link = self.link
            return link.get_id() if id else link
        else:
            return self.value

    def get_link(self, value):
        if is_resolved(value):
            return value

        return self.resource.space.resolve(self.type, value)

    def validate(self, type, value):
        return validate(type, value)

    def set_value(self, value, set_inverse=True):
        self.validate(self.type, value)
        if self.is_link:
            if is_resolved(value):
                # resource given -> get ID or IDs
                link = value
                value = [v.get_id() for v in value] if self.is_list else link.get_id()

                self.value = value
                self.__dict__["link"] = link
                if set_inverse and self.inverse:
                    self.set_inverse(link)
            else:
                # id or ids given -> resolve links later
                self.value = value
                self.__dict__.pop("link", None)
        else:
            # simple assignment without links
            self.value = value

    def set_inverse(self, value):
        resource = self.resource
        if not isinstance(value, list):
            value = [value]

        for v in value:
            inverse = getattr(v, self.inverse)
            if inverse.is_list:
                inverse.add_value(resource, set_inverse=False)
            else:
                inverse.set_value(resource, set_inverse=False)

    def add_value(self, new_value, set_inverse=True, index=None):
        if self.is_list:
            value = self.value
            link = None

            if value is None:
                value = self.value = []

            if not isinstance(new_value, list):
                new_value = [new_value]

            ids = None
            link = None
            if self.is_link:
                link = self.link
                ids = set([v.get_id() for v in link])

            news = []
            for v in new_value:
                if self.is_link:
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
    def link(self):
        return self.get_link(self.value)
