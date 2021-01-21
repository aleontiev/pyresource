from tt import BooleanExpression
from .exceptions import ExpressionValidationError
from .utils import coerce_query_values, coerce_query_value


NOT = 'not'
AND = 'and'
OR = 'or'
UNARY_OPERATORS = {NOT}
BINARY_OPERATORS = {AND, OR}
BOOLEAN_OPERATORS = UNARY_OPERATORS | BINARY_OPERATORS
SIMPLE_EXPRESSIONS = {AND, OR}


def build_expression(expression, mapping):
    """Build a nested dict encoding of a boolean expression

    Arguments:
        expression: boolean expression with whitespace, parens, symbols and operators
            example: a and b or c
        mapping: should resolve all symbols in expression
            example: {"a": 1, "b": 2, "c": 3}
    Returns:
        example:
            {"or": [3, {"and": [1, 2]}]}
    """
    expression = BooleanExpression(expression)
    symbols = expression.symbols
    undefined = set(symbols) - mapping.keys()
    if undefined:
        undefined = ', '.join(undefined)
        raise ExpressionValidationError(
            f'Undefined values in expression: {undefined}'
        )
    return _build_expression(expression, mapping)


def _build_expression(expression, mapping):
    if isinstance(expression, BooleanExpression):
        tree = expression.tree
    else:
        tree = expression

    symbol = tree.symbol_name
    if not (tree.is_dnf or tree.is_cnf):
        tree = tree.to_cnf()

    operator = getattr(tree, 'operator', None)
    if operator:
        key = symbol
        if symbol in UNARY_OPERATORS:
            return {
                key: _build_expression(tree.l_child, mapping)
            }

        clauses = dnf = cnf = None
        if tree.is_dnf:
            clauses = dnf = list(tree.iter_dnf_clauses())
        if tree.is_cnf:
            clauses = cnf = list(tree.iter_cnf_clauses())
        if tree.is_dnf and tree.is_cnf:
            if len(dnf) > len(cnf):
                # go for longer chain
                clauses = dnf
            else:
                clauses = cnf
        return {
            key: [
                _build_expression(operand, mapping) for operand in clauses
            ]
        }
    else:
        return mapping[symbol]


class WhereQueryMixin:

    @classmethod
    def update_where(cls, query, leveled):
        for level, wheres in leveled.items():
            expression = 'and'
            operands = {}
            for i, where in enumerate(wheres):
                num_parts = len(where)
                with_level = f'.{level}' if level else ''
                separator = ':'
                with_remainder = separator + separator.join(where[:-1]) if num_parts > 1 else ''
                original = f"where{with_level}{with_remainder}"
                key = operand = None
                if num_parts == 1:
                    # where=a and b
                    value = where[0]
                    if len(value) > 1:
                        value = ', '.join(value)
                        raise QueryValidationError(
                            f'Invalid where key "{original}", multiple values provided'
                        )
                    value = value[0]
                    expression = value
                elif num_parts == 2:
                    # where:name=Joe
                    # -> {"name": "Joe"}
                    operand = {
                        '=': [where[0], coerce_query_values(where[1], singletons=False)]
                    }
                    key = str(i)
                elif num_parts == 3:
                    # where:name:equals=Joe
                    # -> {"equals": ["name", "Joe"]}}
                    operand = {
                        where[1]: [where[0], coerce_query_values(where[2], singletons=False)]
                    }
                    key = str(i)
                elif num_parts == 4:
                    # where:name:equals:tag=Joe
                    operand = {
                        where[1]: [
                            where[0], coerce_query_values(where[3], singletons=False)
                        ]
                    }
                    key = where[2]
                    if key in BOOLEAN_OPERATORS:
                        raise QueryValidationError(
                            f'Invalid where key "{original}", using operator "{key}"'
                        )
                else:
                    raise QueryValidationError(
                        f'Invalid where key "{original}", too many segments'
                    )
                if operand and key:
                    if key in operands:
                        raise QueryValidationError(
                            f'Invalid where keys, duplicate tags for "{key}"'
                        )
                    operands[key] = operand

            values = list(operands.values())
            if expression not in SIMPLE_EXPRESSIONS:
                # expression specified, try to build it
                update = build_expression(expression, operands)
            else:
                # no expression given, implicit AND
                if len(values) == 1:
                    # simplest case: just one condition
                    update = values
                else:
                    # many conditions
                    update = {expression: values}

            if len(update) == 1:
                update = update[0]

            update = {'where': update}
            query._update(
                update,
                level=level,
                merge=False,
                copy=False
            )
