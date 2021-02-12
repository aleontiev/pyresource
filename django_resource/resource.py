from .expression import execute
from .utils import as_dict, cached_property
from .exceptions import SchemaResolverError, ResourceMisconfigured, FieldMisconfigured
from .store import get_store_class
from .schemas import ResourceSchema


class Resource(object):
    class Schema(ResourceSchema):
        pass

    def __repr__(self):
        return str(self)

    def __str__(self):
        id = self.get_id()
        return f"({self.__class__.__name__}: {id})"

    def __hash__(self):
        return hash(str(self))

    def __init__(self, **options):
        # initialization is lazy; arguments are saved and nothing else

        # make sure there is a schema and a name
        assert self.Schema.name is not None
        # setup: whether or not this instance has been "setup" (actual initialization)
        self._setup = False
        # options: the initial options
        self._options = options
        # attributes: map of local attributes (using Field class)
        self._attributes = {}
        # fields: map of resource fields (using Field class)
        self._fields = {}

        if self.get_meta('id') == 'resources':
            space = self.get_option('space')
            if space.name != '.':
                # normal resources trigger a binding with their space
                # on initialization, do this by calling self.space
                assert self.space is not None

    def __getattr__(self, key):
        if key.startswith("_"):
            return self.__dict__.get(key, None)

        return self.get_attribute(key).get_value()

    def __setattr__(self, key, value):
        if key.startswith("_"):
            return super(Resource, self).__setattr__(key, value)

        field = self.get_attribute(key)
        field.set_value(value)

    def _get_property(self, key):
        """Get attribute (Field) at given key (supporting.nested.paths)

        Raises:
            ValueError if key is not valid
        """
        if key is None:
            return self

        keys = [k for k in key.split(".") if k] if key else []
        value = self
        last = len(keys)
        if not last:
            this = str(self)
            raise ValueError(f"{key} is not a valid field of {this}")
        for i, key in enumerate(keys):
            is_last = i == last
            if key:
                field = value.get_attribute(key)
                if not is_last:
                    value = field.get_value()
        return field

    def serialize(self):
        return {
            key: self.get_property(key)
            for key in self.get_attributes()
        }

    def add(self, key, value, index=None):
        return self._get_property(key).add_value(value, index=index)

    def get_property(self, key=None):
        return self._get_property(key).get_value(resolve=False, id=True)

    def has_option(self, key):
        return key in self._options

    def get_option(self, key, default=None):
        if key in self._options:
            return self._options[key]
        else:
            if callable(default):
                # callable that takes self
                default = default(self)
            elif isinstance(default, dict):
                # expression that takes self
                default, _ = execute(default, {'fields': self})
            return default

    @property
    def pk(self):
        return self.get_id()

    @cached_property
    def fields_by_name(self):
        result = {}
        for record in self.fields:
            result[record.name] = record
        return result

    @cached_property
    def store(self):
        return self.store_class(self)

    @property
    def store_class(self):
        return get_store_class(self.engine)

    @property
    def query(self):
        return self.store.query

    @classmethod
    def get_attributes(cls):
        return cls.Schema.fields

    def get_attribute(self, key):
        from .field import Field
        if key not in self._attributes:
            fields = self.get_attributes()
            if key not in fields:
                raise AttributeError(f"{key} is not a valid property of {self}")

            field = fields[key]
            resource_id = self.get_meta('id')
            id = f"{resource_id}.{key}"

            self._attributes[key] = Field.make(
                parent=self,
                resource=resource_id,
                id=id,
                name=key,
                **field
            )
        return self._attributes[key]

    def get_field_source_names(self):
        resolver = self.store.resolver
        return resolver.get_field_source_names(self.source)

    def get_field(self, key):
        from .field import Field
        if key not in self._fields:
            fields = self.get_option('fields')
            if fields == '*':
                field = {}
            else:
                if not fields or key not in fields:
                    raise AttributeError(f"{key} is not a valid field of {self}")
                field = fields[key]

            resource_id = self.get_id()
            id = f"{resource_id}.{key}"
            resolver = self.store.resolver
            space = None
            if isinstance(field, str) or 'type' not in field:
                # may need self.space to resolve field type
                # for foreign key fields
                space = self.space
            if isinstance(field, dict) and 'source' not in field:
                # add the name as the source
                field['source'] = key

            source = self.get_option('source')
            try:
                field = resolver.get_field_schema(
                    source,
                    field,
                    space=space
                )
            except SchemaResolverError as e:
                exc = str(e)
                raise FieldMisconfigured(f'{id}: {exc}')
            self._fields[key] = Field.make(
                parent=self,
                resource=resource_id,
                id=id,
                name=key,
                **field
            )
        return self._fields[key]

    @classmethod
    def as_record(cls, **kwargs):
        id = cls.get_meta("id")
        fields = cls.get_attributes()
        options = cls.get_meta()
        options["fields"] = ["{}.{}".format(id, key) for key in fields.keys()]
        for key, value in kwargs.items():
            options[key] = value
        return Resource(**options)

    @cached_property
    def id_name(self):
        for field in self.fields:
            if field.primary:
                return field.name

        raise ValueError(f"Resource {self.id} has no primary key field")

    def get_id_attribute(self):
        if getattr(self, "_id_attribute", None):
            return self._id_attribute

        for name, field in self.get_attributes().items():
            if isinstance(field, dict) and field.get("primary", False):
                self._id_attribute = name
                return name

        raise ValueError(f"Resource {self.id} has no ID attribute")

    def get_id(self):
        id_attribute = self.get_id_attribute()
        if id_attribute in self._attributes:
            return getattr(self, id_attribute)

        attribute = self.get_attributes()[id_attribute]
        default = None
        if isinstance(attribute, dict):
            default = attribute.get('default', None)
        return self.get_option(id_attribute, default)

    @classmethod
    def get_meta(cls, key=None, default=None):
        if not key:
            return as_dict(cls.Schema)
        return getattr(cls.Schema, key, default)

    @cached_property
    def urls(self):
        return self.get_urls()

    def get_urls(self):
        """Get Django urlpatterns for this resource"""
        base = self.url
        patterns = [base]
        for field in self.fields:
            patterns.append(f'{base}{field.name}/')
        return patterns


def is_resolved(x):
    if isinstance(x, Resource):
        return True
    if isinstance(x, list) and all((isinstance(c, Resource) for c in x)):
        return True
    if isinstance(x, dict) and all((isinstance(c, Resource) for c in x.values())):
        return True
    return False
