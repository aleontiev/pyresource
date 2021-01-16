from django_resource.exceptions import FilterError
from .operators import compound_operators, query_operators


class DjangoFilter:
    def __init__(self, where):
        self.where = where

    @cached_property
    def value(self):
        return self.get_value()

    def get_value(self):
        if not isinstance(self.where, (dict, list)):
            raise FilterError('"where" must be a dict or list')

        if isinstance(self.where, list):
            where = {'or': self.where}
        else:
            where = self.where

        result = None
        for method, arguments in where.items():
            if method in compound_operators:
                if method == 'or' or method == 'and':
                    if not isinstance(arguments, list):
                        raise FilterError('"or"/"and" argument must be a list')

                    value = [DjangoFilter(argument).value for argument in arguments]
                    return reduce(compound_operators[method], value)
                elif method == 'not':
                    if isinstance(arguments, list) and len(arguments) == 1:
                        arguments = arguments[0]
                    if not isinstance(arguments, dict):
                        raise FilterError('"not" argument must be a dict')

                    return compound_operators[method](value)
            elif method in query_operators:
                operator = query_operators[method]
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

                return method(*arguments)
