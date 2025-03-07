from functional.ffront import field_operator_ast as foast


def compute_assign_indices(
    targets: list[foast.FieldSymbol | foast.TupleSymbol | foast.ScalarSymbol | foast.Starred],
    num_elts: int,
) -> list[tuple[int, int] | int]:
    """
    Compute a list of indices, mapping each target to its respective value(s).

    This function is used when mapping a tuple of targets to a tuple of values, and also handles the
    case in which tuple unpacking is done using a Starred operator.

    Examples
    --------
    The below are examples of different types of unpacking and the generated indices. Note that the
    indices in the tuple correspond to the lower and upper slice indices of a Starred variable.

    ..  code-block:: python

        # example pseudocode
        *a, b, c = (1, 2, 3, 4)
        [(0, 2), 2, 3]

        a, *b, c = (1, 2, 3, 4)
        (0, (1, 3), 3)

        a, b, *c = (1, 2, 3, 4)
        [0, 1, (2, 4)]
    """
    starred_lower, starred_upper = None, None
    for idx, elt in enumerate(targets):
        if isinstance(elt, foast.Starred):
            starred_lower = idx
            break
    for idx, elt in zip(reversed(range(num_elts)), reversed(targets)):
        if isinstance(elt, foast.Starred):
            starred_upper = idx + 1
            break
    if starred_lower is not None and starred_upper is not None:
        return (
            list(range(0, starred_lower))
            + [(starred_lower, starred_upper)]
            + list(range(starred_upper, num_elts))
        )
    return list(range(0, num_elts))  # no starred target
