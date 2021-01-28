import decimal
from django.db.models import Q, F, Value, Count
from django.db.models.functions import Now, Concat, Coalesce, Trunc
from django_resource.exceptions import FilterError, ExpressionError
from django_resource.utils import is_literal, resource_to_django
from django_resource.translator import ResourceTranslator


# core set of operators
compound_operators = {
    'or': lambda a, b: a | b,
    'and': lambda a, b: a & b,
    'not': lambda a: ~a
}


def transform_query_key(key, translate=None):
    if is_literal(key):
        raise ValueError('key cannot be a literal')

    if translate:
        key = ResourceTranslator.translate(key, translate)

    return resource_to_django(key)


def transform_query_value(value):
    if isinstance(value, dict):
        try:
            return make_expression(value)
        except ExpressionError as e:
            raise FilterError(f'Failed to make expression from {value}: {str(e)}')

    if isinstance(value, list):
        return [transform_query_value(v) for v in value]

    if not is_literal(value):
        # field references should be converted to Django F() references
        value = F(value)
    elif isinstance(value, str) and value:
        # strip out 'literal' quoting
        value = value[1:-1]

    # all other literals pass through
    return value


def make_comparison_operator(
    name,
    num_args=2,
    can_invert=True,
    inverse=None,
    transform=None,
    value=None
):
    inverse_str = isinstance(inverse, str)
    def method(a, b=None, translate=None):
        if value is not None:
            b = value

        inverted = False
        filter_name = name
        try:
            key = transform_query_key(a, translate=translate)
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
gt = make_comparison_operator('gt', inverse='lte')
gte = make_comparison_operator('gte', inverse='lt')
lt = make_comparison_operator('lt', inverse='gte')
lte = make_comparison_operator('lte', inverse='gt')
eq = make_comparison_operator('exact')
ne = make_comparison_operator('exact', transform=not_)
contains = make_comparison_operator('contains', can_invert=False)
not_contains = make_comparison_operator('contains', can_invert=False, transform=not_)
icontains = make_comparison_operator('icontains', can_invert=False)
not_icontains = make_comparison_operator('icontains', can_invert=False, transform=not_)
in_ = make_comparison_operator('in', can_invert=False)
not_in = make_comparison_operator('in', can_invert=False, transform=not_)
range_ = make_comparison_operator('range', can_invert=False)
not_range = make_comparison_operator('range', can_invert=False, transform=not_)
isnull = make_comparison_operator('isnull', num_args=1, value=True, can_invert=False)
not_null = make_comparison_operator('isnull', num_args=1, value=False, can_invert=False, transform=not_)
true = make_comparison_operator('exact', num_args=1, value=True, can_invert=False)
false = make_comparison_operator('exact', num_args=1, value=False, can_invert=False)



comparison_operators = {
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


def make_expression_operator(
    base,
    num_args=None,
):
    def method(*args):
        # optionally add other options like `output_field`
        return base(*args)

    return {
        'method': method,
        'num_args': num_args
    }

concat = make_expression_operator(Concat)
count = make_expression_operator(Count, num_args=1)
now = make_expression_operator(Now, num_args=0)
coalesce = make_expression_operator(Coalesce)
trunc = make_expression_operator(Trunc, num_args=2)


expression_operators = {
    'concat': concat,
    'count': count,
    'now': now,
    'trunc': trunc,
    'coalesce': coalesce,
}


def make_literal(value):
    return f'"{value}"'


def make_expression(value):
    if value is None or isinstance(value, (bool, int, float, decimal.Decimal)):
        return Value(value)

    if isinstance(value, str):
        if is_literal(value):
            return Value(value[1:-1])
        else:
            value = resource_to_django(value)
            return F(value)

    if not isinstance(value, dict):
        raise ExpressionError(f'value must be a dict or literal, not {value}')

    result = None
    operators = expression_operators
    for method, arguments in value.items():
        if method in compound_operators:
            if method == 'or' or method == 'and':
                if not isinstance(arguments, list):
                    raise ExpressionError('"or"/"and" argument must be a list')

                value = [make_expression(argument) for argument in arguments]
                return reduce(compound_operators[method], value)
            elif method == 'not':
                if isinstance(arguments, list) and len(arguments) == 1:
                    arguments = arguments[0]
                if not isinstance(arguments, dict):
                    raise Expression('"not" argument must be a dict')

                value = make_expression(value)
                return compound_operators[method](value)
        elif method in operators:
            operator = operators[method]
            num_args = operator.get('num_args', None)
            fn = operator['method']
            if num_args is None:
                pass  # any number of arguments accepted
            elif num_args == 0:
                if arguments:
                    raise ExpressionError(f'"{method}" arguments not expected: {arguments}')
                arguments = []
            elif num_args == 1:
                if isinstance(arguments, list):
                    if len(arguments) != 1:
                        raise ExpressionError(
                            f'"{method}" arguments must be a list of size 1 or non-list value.\n'
                            f'Instead got: {arguments}'
                        )

            else:
                if not isinstance(arguments, list) or not len(arguments) == num_args:
                    raise ExpressionError(
                        f'"{method}" arguments must be a list of size {num_args}.\n'
                        f'Instead got: {arguments}'
                    )

            if not isinstance(arguments, list):
                arguments = [arguments]

            arguments = [make_expression(argument) for argument in arguments]
            return fn(*arguments)
        else:
            raise ExpressionError(
                f'"{method}" is not a valid expression'
            )


def make_filter(where, translate=None):
    if not isinstance(where, (dict, list)):
        raise FilterError('"where" must be a dict or list')

    if isinstance(where, list):
        where = {'or': where}

    result = None
    for method, arguments in where.items():
        if method in compound_operators:
            if method == 'or' or method == 'and':
                if not isinstance(arguments, list):
                    raise FilterError('"or"/"and" argument must be a list')

                value = [make_filter(argument, translate=translate) for argument in arguments]
                return reduce(compound_operators[method], value)
            elif method == 'not':
                if isinstance(arguments, list) and len(arguments) == 1:
                    arguments = arguments[0]
                if not isinstance(arguments, dict):
                    raise FilterError('"not" argument must be a dict')

                return compound_operators[method](value)
        elif method in comparison_operators:
            operator = comparison_operators[method]
            num_args = operator.get('num_args', 0)
            method = operator['method']
            if num_args == 0:
                if arguments:
                    raise FilterError(f'"{method}" arguments not expected: {arguments}')
                arguments = []

            elif num_args == 1:
                if isinstance(arguments, list):
                    if len(arguments) != 1:
                        raise FilterError(
                            f'"{method}" arguments must be a list of size 1 or non-list value.\n'
                            f'Instead got: {arguments}'
                        )

            elif num_args == 2:
                if not isinstance(arguments, list) or not len(arguments) == num_args:
                    raise FilterError(
                        f'"{method}" arguments must be a list of size {num_args}.\n'
                        f'Instead got: {arguments}'
                    )

            else:
                raise FilterError(
                    'Only binary/unary/simple callables are supported at this time'
                )

            if not isinstance(arguments, list):
                arguments = [arguments]
            return method(*arguments, translate=translate)
        else:
            raise FilterError(
                f'{method} is not a valid filter'
            )
