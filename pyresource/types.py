from .resource import Resource
from decimal import Decimal
from .schemas import TypeSchema
from .utils.types import is_container


class Type(Resource):
    class Schema(TypeSchema):
        pass

    @classmethod
    def get_base_type(cls, name, server=None):
        kwargs = {
            "name": name,
            "base": "any",
            "container": is_container(name)
        }
        if server:
            kwargs["server"] = server
        return cls(**kwargs)
