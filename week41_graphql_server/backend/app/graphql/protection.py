import graphql
from graphql.language.ast import (
    FieldNode,
    InlineFragmentNode,
    OperationDefinitionNode,
)

LIST_FIELDS = {"users", "projects", "technologies", "reviews"}


def get_selection_depth(selection_set, fragments=None, current_depth=1):
    """Recursively calculates max depth across selections in AST."""
    if not selection_set or not selection_set.selections:
        return current_depth

    max_depth = current_depth
    for selection in selection_set.selections:
        if isinstance(selection, FieldNode):
            # Do not increment depth for introspection meta fields
            if selection.name.value.startswith("__"):
                continue
            if selection.selection_set:
                child_depth = get_selection_depth(
                    selection.selection_set,
                    fragments=fragments,
                    current_depth=current_depth + 1,
                )
                if child_depth > max_depth:
                    max_depth = child_depth
        elif isinstance(selection, InlineFragmentNode):
            child_depth = get_selection_depth(
                selection.selection_set,
                fragments=fragments,
                current_depth=current_depth,
            )
            if child_depth > max_depth:
                max_depth = child_depth
    return max_depth


def calculate_query_depth(document_ast):
    """Calculates maximum field nesting depth in a GraphQL document AST."""
    max_depth = 0
    fragments = {}
    for definition in document_ast.definitions:
        if hasattr(definition, "name") and definition.name:
            if definition.__class__.__name__ == "FragmentDefinitionNode":
                fragments[definition.name.value] = definition

    for definition in document_ast.definitions:
        if isinstance(definition, OperationDefinitionNode):
            op_depth = get_selection_depth(
                definition.selection_set, fragments=fragments, current_depth=1
            )
            if op_depth > max_depth:
                max_depth = op_depth
    return max_depth


def calculate_selection_complexity(selection_set, multiplier=1, fragments=None):
    """Calculates cumulative complexity score of field selections."""
    if not selection_set or not selection_set.selections:
        return 0

    cost = 0
    for selection in selection_set.selections:
        if isinstance(selection, FieldNode):
            field_name = selection.name.value
            if field_name.startswith("__"):
                continue

            field_multiplier = multiplier
            if field_name in LIST_FIELDS:
                field_cost = 5 * multiplier
                field_multiplier = multiplier * 2
            elif selection.selection_set:
                field_cost = 2 * multiplier
            else:
                field_cost = 1 * multiplier

            cost += field_cost
            if selection.selection_set:
                cost += calculate_selection_complexity(
                    selection.selection_set,
                    multiplier=field_multiplier,
                    fragments=fragments,
                )
        elif isinstance(selection, InlineFragmentNode):
            cost += calculate_selection_complexity(
                selection.selection_set,
                multiplier=multiplier,
                fragments=fragments,
            )
    return cost


def calculate_query_complexity(document_ast):
    """Calculates total estimated query complexity for a document AST."""
    total_cost = 0
    for definition in document_ast.definitions:
        if isinstance(definition, OperationDefinitionNode):
            total_cost += calculate_selection_complexity(definition.selection_set)
    return total_cost


def validate_query_safety(query_str, max_depth=7, max_complexity=300):
    """
    Parses and checks GraphQL query string against depth and complexity limits.
    Returns (is_safe, error_message, depth, complexity).
    """
    try:
        document_ast = graphql.parse(query_str)
    except Exception:
        # Let syntax errors be caught by Graphene's execution parser
        return True, None, 1, 1

    depth = calculate_query_depth(document_ast)
    complexity = calculate_query_complexity(document_ast)

    if depth > max_depth:
        msg = (
            f"Query depth of {depth} exceeds the maximum allowed depth "
            f"limit of {max_depth}."
        )
        return False, msg, depth, complexity

    if complexity > max_complexity:
        msg = (
            f"Query complexity of {complexity} exceeds maximum allowed "
            f"limit of {max_complexity}."
        )
        return False, msg, depth, complexity

    return True, None, depth, complexity
