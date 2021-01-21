from django.db.models import Q, F
from django_resource.exceptions import FilterError
from django.db.models.functions import Now


# core set of operators
compound_operators = {
    'or': lambda a, b: a | b,
    'and': lambda a, b: a & b,
    'not': lambda a: ~a
}

def is_literal(key):
    if not isinstance(key, str):
        return True
    # for strings
    if key and key.startswith('"') or key.startswith("'") and key[0] == key[-1]:
        return True
    return False


def transform_query_key(key):
    if is_literal(key):
        raise ValueError('key cannot be a literal')
    return key.replace('.', '__')


def transform_query_value(value):
    if isinstance(value, dict):
        # Django functions
        if len(value) > 1:
            raise FilterError('Not expecting multiple keys in function')
        method = next(iter(value))
        if method == 'now':
            return Now()
        else:
            # TODO support majority of Django functions from 3.x:
            # trunc, concat
            raise FilterError(f'Filter transform/function "{method}" is not supported')
    if isinstance(value, list):
        return [transform_value(v) for v in value]

    if not is_literal(value):
        # field references should be converted to Django F() references
        value = F(value)
    elif isinstance(value, str) and value:
        # strip out 'literal' quoting
        value = value[1:-1]

    # all other literals pass through
    return value


def make_query_operator(
    name,
    num_args=2,
    can_invert=True,
    inverse=None,
    transform=None,
    value=None
):
    inverse_str = isinstance(inverse, str)
    def method(a, b=None):
        if value is not None:
            b = value

        inverted = False
        filter_name = name
        try:
            key = transform_query_key(a)
            val = transform_query_value(b)
        except ValueError:
            try:
                if not can_invert:
                    raise FilterError(
                        'Cannot invert {name} filter and LHS is a literal: {a}'
                    )

                key = transform_query_key(b)
                val = transform_query_value(b)
                inverted = True
                if inverse_str:
                    filter_name = inverse
            except ValueError:
                raise FilterError(
                    'Cannot build a {name} filter from two literals: {a} and {b}'
                , transform=None)

        q = Q(**{f'{key}__{name}': val})
        if transform:
            # apply functional transform to Q object
            q = transform(q)

        if inverted and not inverse_str:
            # apply functional transform to Q object (inverted)
            q = inverse(q)
        return q

    return {
        'method': method,
        'num_args': num_args
    }


not_ = compound_operators['not']
gt = make_query_operator('gt', inverse='lte')
gte = make_query_operator('gte', inverse='lt')
lt = make_query_operator('lt', inverse='gte')
lte = make_query_operator('lte', inverse='gt')
eq = make_query_operator('exact')
ne = make_query_operator('exact', transform=not_)
contains = make_query_operator('contains', can_invert=False)
not_contains = make_query_operator('contains', can_invert=False, transform=not_)
icontains = make_query_operator('icontains', can_invert=False)
not_icontains = make_query_operator('icontains', can_invert=False, transform=not_)
in_ = make_query_operator('in', can_invert=False)
not_in = make_query_operator('in', can_invert=False, transform=not_)
range_ = make_query_operator('range', can_invert=False)
not_range = make_query_operator('range', can_invert=False, transform=not_)
isnull = make_query_operator('isnull', num_args=1, value=True, can_invert=False)
not_null = make_query_operator('isnull', num_args=1, value=False, can_invert=False, transform=not_)
true = make_query_operator('exact', num_args=1, value=True, can_invert=False)
false = make_query_operator('exact', num_args=1, value=False, can_invert=False)



query_operators = {
    '>=': gte,
    'gte': gte,
    '>': gt,
    'gt': gt,
    '<': lt,
    'lt': lt,
    'lte': lte,
    '<=': lte,
    '=': eq,
    'eq': eq,
    '!=': ne,
    'ne': ne,
    'in': in_,
    '-in': not_in,
    'range': range_,
    '-range': not_range,
    'not.range': not_range,
    'isnull': isnull,
    'null': isnull,
    '-null': not_null,
    'not.null': not_null,
    'contains': contains,
    '-contains': not_contains,
    'icontains': icontains,
    '-icontains': not_icontains,
    'true': true,
    'false': false
}
