from .utils import cached_property
from .utils.types import is_list, get_link, validate, is_nullable
from .resource import Resource
from .expression import execute
from .schemas import FieldSchema
from .exceptions import TypeValidationError


def is_resolved(x):
    if isinstance(x, Resource):
        return True
    if isinstance(x, list) and all((isinstance(c, Resource) for c in x)):
        return True
    if isinstance(x, dict) and all((isinstance(c, Resource) for c in x.values())):
        return True
    return False


class Field(Resource):
    class Schema(FieldSchema):
        pass
    def __init__(self, *args, **kwargs):
        super(Field, self).__init__(*args, **kwargs)
        type = self.get_option('type')
        self._is_link = get_link(type)
        self._is_list = is_list(type)
        self._is_nullable = is_nullable(type)

    @property
    def is_link(self):
        return self._is_list

    @property
    def is_list(self):
        return self._is_list

    @property
    def is_nullable(self):
        return self._is_nullable

    def setup(self):
        if not self._setup:
            # set initial value via parent
            source = self.get_option('source')
            type = self.get_option('type')
            name = self.get_option('name')
            id = self.get_option('id')

            if source:
                # get value from source expression
                value = self.get_from_expression(source)
            else:
                # get value from parent by name
                default = self.get_option('default')
                value = self.parent.get_option(name, default)

            # transform field spec dict into field array
            if (
                id == 'resources.fields'
            ):
                if value == '*':
                    value = {k: True for k in self.parent.get_field_source_names()}

                if isinstance(value, dict):
                    value = [self.parent.get_field(name) for name in value]

            self.set_value(value)

    def get_from_expression(self, source):
        return execute(source, {'fields': self.parent})

    @cached_property
    def related(self):
        link = self._is_link
        if not link:
            return None
        if '.' in link:
            # link is resource ID
            return self.space.server.get_resource_by_id(link)
        else:
            # link is resource name referencing the current space
            return self.space.resources_by_name.get(link)

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

    @property
    def space(self):
        return self.get_space()

    def get_space(self):
        from .space import Space

        space = None
        parent = self.parent
        space = parent.get_option('space')
        if space and (
            space == '.' or
            (isinstance(space, Space) and space.name == '.')
        ):
            # get root space
            parent_name = parent.get_meta_attribute('name')
            while parent_name == 'fields':
                parent = parent.parent
                parent_name = parent.get_meta_attribute('name')

            if parent_name == 'server':
                space = parent.root
            elif parent_name == 'resources':
                space = parent.get_option('space')
                if not is_resolved(space):
                    space = parent.space
                space = space.server.root
            elif parent_name == 'spaces':
                space = parent.server.root
            elif parent_name == 'types':
                space = parent.server.root
        else:
            # get space from parent resource
            space = parent.space
        return space

    def get_link(self, value):
        if is_resolved(value):
            return value

        return self.space.resolve(self.type, value)

    def validate(self, type, value):
        try:
            return validate(type, value)
        except TypeValidationError as e:
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
            inverse_field = v.get_attribute(inverse)
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
