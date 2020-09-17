from tt import BooleanExpression
from .exceptions import ExpressionValidationError

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
