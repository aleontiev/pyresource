from .resource import Resource
from .exceptions import ValidationError


class Type(Resource):
    _resource = None
    _schema = {
    }


CONTAINERS = {
    '{',
    '[',
    '?'
}


def is_list(T):
    if T and isinstance(T, str):
        return T.startswith('[') or T.startswith('?[')
    elif isinstance(T, list):
        return all([is_list(t) for t in T])
    elif isinstance(T, dict):
        return all([is_list(t) for t in T.values()])
    return False


def is_link(T):
    if T and isinstance(T, str):
        return '@' in T
    elif isinstance(T, list):
        return all([is_link(t) for t in T])
    elif isinstance(T, dict):
        return all([is_link(t) for t in T.values()])
    return False


def get_link(T):
    link = is_link(T)
    if link:
        return True, ''.join(T[T.index('@') + 1:])
    else:
        return None, None


def get_container(T):
    if T and isinstance(T, str):
        if T[0] in CONTAINERS:
            return T[0], T[1:]
        else:
            return None, T
    else:
        return None, T


def validate(type, value):
    if isinstance(type, list):
        return any((validate(t, value) for t in type))
    if isinstance(type, dict):
        return all((validate(t, value.get(k)) for k, t in type.items()))
    container, remainder = get_container(type)
    if container:
        expecting = None
        label = None
        if container == '[':
            expecting = list
            label = 'array'
        elif container == '{':
            expecting = dict
            label = 'object'

        if expecting and not isinstance(value, expecting):
            raise ValidationError(f'expecting {label} but got: {value}')

        if remainder:
            # validate remainder
            if container == '[':
                return all((validate(remainder, v) for v in value))
            elif container == '{':
                return all((validate(remainder, v) for v in value.items()))
            elif container == '?':
                return (value is None) or validate(remainder, value)
        else:
            return True
    else:
        # base validation
        expecting = None
        if type == 'number':
            expecting = (int, float)
        elif type == 'string':
            expecting = str
        elif type == 'any':
            expecting = None
        elif type == 'boolean':
            expecting = bool
        elif type.startswith('@'):
            expecting = None

        if expecting and not isinstance(value, expecting):
            raise ValidationError(f'expecting {type} but got: {value}')

        return True

