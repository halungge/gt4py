import dataclasses
from collections import ChainMap
from typing import Optional

from eve import NodeTranslator, NodeVisitor
from eve.utils import UIDGenerator
from functional.iterator import ir


class CollectSubexpressions(NodeVisitor):
    @classmethod
    def apply(cls, node: ir.Node):
        subexprs = dict[ir.Node, tuple[list[int], Optional[ir.Node]]]()
        refs: ChainMap[str, bool] = ChainMap()
        collector_stack: list[bool] = []

        cls().visit(
            node, subexprs=subexprs, refs=refs, parent=None, collector_stack=collector_stack
        )

        return subexprs

    def visit_SymRef(
        self,
        node: ir.SymRef,
        *,
        refs: ChainMap[str, bool],
        collector_stack: list[bool],
        **kwargs,
    ) -> None:
        if node.id in refs:
            # we have used a symbol that is not declared in the root node, so propagate
            # to parent
            collector_stack[-1] = False

    def visit_Lambda(
        self,
        node: ir.Lambda,
        *,
        subexprs: dict[ir.Node, tuple[list[int], Optional[ir.Node]]],
        refs: ChainMap[str, bool],
        parent: Optional[ir.Node],
        collector_stack: list[bool],
    ) -> None:
        r = refs.new_child({p.id: False for p in node.params})

        child_collector_stack = [*collector_stack, True]
        self.generic_visit(
            node, subexprs=subexprs, refs=r, parent=node, collector_stack=child_collector_stack
        )
        if child_collector_stack[-1]:
            subexprs.setdefault(node, ([], parent))[0].append(id(node))
        else:
            if len(collector_stack) > 0:
                collector_stack[-1] = False  # poison parent

    def visit_FunCall(
        self,
        node: ir.FunCall,
        *,
        subexprs: dict[ir.Node, tuple[list[int], Optional[ir.Node]]],
        refs: ChainMap[str, bool],
        parent: Optional[ir.Node],
        collector_stack: list[bool],
    ) -> None:
        # do not collect (and thus deduplicate in CSE) shift(offsets…) calls. Node must still be
        #  visited, to ensure symbol dependencies are recognized correctly.
        allow_collection = node.fun != ir.SymRef(id="shift")
        child_collector_stack = [*collector_stack, allow_collection]

        self.generic_visit(
            node, subexprs=subexprs, refs=refs, parent=node, collector_stack=child_collector_stack
        )

        if child_collector_stack[-1]:
            subexprs.setdefault(node, ([], parent))[0].append(id(node))
        else:
            if len(collector_stack) > 0:
                collector_stack[-1] = False  # poison parent


@dataclasses.dataclass(frozen=True)
class CommonSubexpressionElimination(NodeTranslator):
    """
    Perform common subexpression elimination.

    Examples:
        >>> x = ir.SymRef(id="x")
        >>> plus_ = lambda a, b: ir.FunCall(fun=ir.SymRef(id=("plus")), args=[a, b])
        >>> expr = plus_(plus_(x, x), plus_(x, x))
        >>> print(CommonSubexpressionElimination().visit(expr))
        (λ(_cs_1) → _cs_1 + _cs_1)(x + x)
    """

    # we use one UID generator per instance such that the generated ids are
    # stable across multiple runs (required for caching to properly work)
    uids: UIDGenerator = dataclasses.field(init=False, repr=False, default_factory=UIDGenerator)

    def visit_FunCall(self, node: ir.FunCall):
        if isinstance(node.fun, ir.SymRef) and node.fun.id in [
            "cartesian_domain",
            "unstructured_domain",
        ]:
            return node

        # collect expressions
        subexprs = CollectSubexpressions.apply(node)

        # collect multiple occurrences and map them to fresh symbols
        expr_map = dict[int, ir.SymRef]()
        params = []
        args = []
        for expr, (ids, parent) in subexprs.items():
            if len(ids) > 1:
                # ignore if parent will be eliminated anyway
                if parent and parent in subexprs and len(subexprs[parent][0]) > 1:
                    continue
                expr_id = self.uids.sequential_id(prefix="_cs")
                params.append(ir.Sym(id=expr_id))
                args.append(expr)
                expr_ref = ir.SymRef(id=expr_id)
                for i in ids:
                    expr_map[i] = expr_ref

        if not expr_map:
            return self.generic_visit(node)

        # apply remapping
        class Replace(NodeTranslator):
            def visit_Expr(self, node):
                if id(node) in expr_map:
                    return expr_map[id(node)]
                return self.generic_visit(node)

        return self.generic_visit(
            ir.FunCall(
                fun=ir.Lambda(params=params, expr=Replace().visit(node)),
                args=args,
            )
        )
