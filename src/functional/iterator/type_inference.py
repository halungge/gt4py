import typing
from collections import abc

import eve
from functional.iterator import ir
from functional.type_inference import Type, TypeVar, freshen, reindex_vars, unify


"""Constraint-based inference for the iterator IR."""

T = typing.TypeVar("T", bound="Type")


class EmptyTuple(Type):
    def __iter__(self) -> abc.Iterator[Type]:
        return
        yield


class Tuple(Type):
    """Tuple type with arbitrary number of elements."""

    front: Type
    others: Type

    @classmethod
    def from_elems(cls: typing.Type[T], *elems: Type) -> typing.Union[T, EmptyTuple]:
        tup: typing.Union[T, EmptyTuple] = EmptyTuple()
        for e in reversed(elems):
            tup = cls(front=e, others=tup)
        return tup

    def __iter__(self) -> abc.Iterator[Type]:
        yield self.front
        if not isinstance(self.others, (Tuple, EmptyTuple)):
            raise ValueError(f"Can not iterate over partially defined tuple {self}")
        yield from self.others


class FunctionType(Type):
    """Function type.

    Note: the type inference algorithm always infers a tuple-like type for
    `args`, even for single-argument functions.
    """

    args: Type = eve.field(default_factory=TypeVar.fresh)
    ret: Type = eve.field(default_factory=TypeVar.fresh)


class Val(Type):
    """The main type for representing values and iterators.

    Each `Val` consists of the following three things:
    - A `kind` which is either `Value()`, `Iterator()`, or a variable
    - A `dtype` which is either a `Primitive` or a variable
    - A `size` which is either `Scalar()`, `Column()`, or a variable
    """

    kind: Type = eve.field(default_factory=TypeVar.fresh)
    dtype: Type = eve.field(default_factory=TypeVar.fresh)
    size: Type = eve.field(default_factory=TypeVar.fresh)


class ValTuple(Type):
    """A tuple of `Val` where all items have the same `kind` and `size`, but different dtypes."""

    kind: Type = eve.field(default_factory=TypeVar.fresh)
    dtypes: Type = eve.field(default_factory=TypeVar.fresh)
    size: Type = eve.field(default_factory=TypeVar.fresh)

    def __eq__(self, other: typing.Any) -> bool:
        if isinstance(self.dtypes, Tuple) and isinstance(other, Tuple):
            dtypes: Type = self.dtypes
            elems: Type = other
            while (
                isinstance(dtypes, Tuple)
                and isinstance(elems, Tuple)
                and Val(kind=self.kind, dtype=dtypes.front, size=self.size) == elems.front
            ):
                dtypes = dtypes.others
                elems = elems.others
            return dtypes == elems == EmptyTuple()

        return (
            isinstance(other, ValTuple)
            and self.kind == other.kind
            and self.dtypes == other.dtypes
            and self.size == other.size
        )

    def handle_constraint(
        self, other: Type, add_constraint: abc.Callable[[Type, Type], None]
    ) -> bool:
        if isinstance(other, Tuple):
            dtypes = [TypeVar.fresh() for _ in other]
            expanded = [Val(kind=self.kind, dtype=dtype, size=self.size) for dtype in dtypes]
            add_constraint(self.dtypes, Tuple.from_elems(*dtypes))
            add_constraint(Tuple.from_elems(*expanded), other)
            return True
        if isinstance(other, EmptyTuple):
            add_constraint(self.dtypes, EmptyTuple())
            return True
        return False


class Column(Type):
    """Marker for column-sized values/iterators."""

    ...


class Scalar(Type):
    """Marker for scalar-sized values/iterators."""

    ...


class Primitive(Type):
    """Primitive type used in values/iterators."""

    name: str

    def handle_constraint(
        self, other: Type, add_constraint: abc.Callable[[Type, Type], None]
    ) -> bool:
        if not isinstance(other, Primitive):
            return False

        if self.name != other.name:
            raise TypeError(
                f"Can not satisfy constraint on primitive types: {self.name} ≡ {other.name}"
            )
        return True


class Value(Type):
    """Marker for values."""

    ...


class Iterator(Type):
    """Marker for iterators."""

    ...


class Closure(Type):
    """Stencil closure type."""

    output: Type
    inputs: Type


class FunctionDefinitionType(Type):
    """Function definition type."""

    name: str
    fun: FunctionType


class FencilDefinitionType(Type):
    """Fencil definition type."""

    name: str
    fundefs: Type
    params: Type


class LetPolymorphic(Type):
    """Wrapper for let-polymorphic types.

    Used for fencil-level function definitions.
    """

    dtype: Type


BOOL_DTYPE = Primitive(name="bool")
INT_DTYPE = Primitive(name="int")
FLOAT_DTYPE = Primitive(name="float")
AXIS_DTYPE = Primitive(name="axis")
NAMED_RANGE_DTYPE = Primitive(name="named_range")
DOMAIN_DTYPE = Primitive(name="domain")

# Some helpers to define the builtins’ types
T0 = TypeVar.fresh()
T1 = TypeVar.fresh()
T2 = TypeVar.fresh()
It_T0_T1 = Val(kind=Iterator(), dtype=T0, size=T1)
Val_T0_T1 = Val(kind=Value(), dtype=T0, size=T1)
Val_T0_Scalar = Val(kind=Value(), dtype=T0, size=Scalar())
Val_BOOL_T1 = Val(kind=Value(), dtype=BOOL_DTYPE, size=T1)

BUILTIN_TYPES: typing.Final[dict[str, Type]] = {
    "deref": FunctionType(
        args=Tuple.from_elems(
            It_T0_T1,
        ),
        ret=Val_T0_T1,
    ),
    "can_deref": FunctionType(
        args=Tuple.from_elems(
            It_T0_T1,
        ),
        ret=Val_BOOL_T1,
    ),
    "plus": FunctionType(args=Tuple.from_elems(Val_T0_T1, Val_T0_T1), ret=Val_T0_T1),
    "minus": FunctionType(args=Tuple.from_elems(Val_T0_T1, Val_T0_T1), ret=Val_T0_T1),
    "multiplies": FunctionType(args=Tuple.from_elems(Val_T0_T1, Val_T0_T1), ret=Val_T0_T1),
    "divides": FunctionType(args=Tuple.from_elems(Val_T0_T1, Val_T0_T1), ret=Val_T0_T1),
    "eq": FunctionType(args=Tuple.from_elems(Val_T0_T1, Val_T0_T1), ret=Val_BOOL_T1),
    "less": FunctionType(args=Tuple.from_elems(Val_T0_T1, Val_T0_T1), ret=Val_BOOL_T1),
    "greater": FunctionType(args=Tuple.from_elems(Val_T0_T1, Val_T0_T1), ret=Val_BOOL_T1),
    "and_": FunctionType(args=Tuple.from_elems(Val_BOOL_T1, Val_BOOL_T1), ret=Val_BOOL_T1),
    "or_": FunctionType(args=Tuple.from_elems(Val_BOOL_T1, Val_BOOL_T1), ret=Val_BOOL_T1),
    "xor_": FunctionType(args=Tuple.from_elems(Val_BOOL_T1, Val_BOOL_T1), ret=Val_BOOL_T1),
    "not_": FunctionType(
        args=Tuple.from_elems(
            Val_BOOL_T1,
        ),
        ret=Val_BOOL_T1,
    ),
    "if_": FunctionType(args=Tuple.from_elems(Val_BOOL_T1, Val_T0_T1, Val_T0_T1), ret=Val_T0_T1),
    "cast_": FunctionType(args=Tuple.from_elems(Val_T0_T1, Val_T0_T1), ret=Val_T0_T1),
    "lift": FunctionType(
        args=Tuple.from_elems(
            FunctionType(args=ValTuple(kind=Iterator(), dtypes=T2, size=T1), ret=Val_T0_T1)
        ),
        ret=FunctionType(args=ValTuple(kind=Iterator(), dtypes=T2, size=T1), ret=It_T0_T1),
    ),
    "reduce": FunctionType(
        args=Tuple.from_elems(
            FunctionType(
                args=Tuple(front=Val_T0_T1, others=ValTuple(kind=Value(), dtypes=T2, size=T1)),
                ret=Val_T0_T1,
            ),
            Val_T0_T1,
        ),
        ret=FunctionType(args=ValTuple(kind=Iterator(), dtypes=T2, size=T1), ret=Val_T0_T1),
    ),
    "scan": FunctionType(
        args=Tuple.from_elems(
            FunctionType(
                args=Tuple(
                    front=Val_T0_Scalar,
                    others=ValTuple(kind=Iterator(), dtypes=T2, size=Scalar()),
                ),
                ret=Val_T0_Scalar,
            ),
            Val(kind=Value(), dtype=BOOL_DTYPE, size=Scalar()),
            Val_T0_Scalar,
        ),
        ret=FunctionType(
            args=ValTuple(kind=Iterator(), dtypes=T2, size=Column()),
            ret=Val(kind=Value(), dtype=T0, size=Column()),
        ),
    ),
    "named_range": FunctionType(
        args=Tuple.from_elems(
            Val(kind=Value(), dtype=AXIS_DTYPE, size=Scalar()),
            Val(kind=Value(), dtype=INT_DTYPE, size=Scalar()),
            Val(kind=Value(), dtype=INT_DTYPE, size=Scalar()),
        ),
        ret=Val(kind=Value(), dtype=NAMED_RANGE_DTYPE, size=Scalar()),
    ),
}

del T0, T1, T2, It_T0_T1, Val_T0_T1, Val_T0_Scalar, Val_BOOL_T1


class _TypeInferrer(eve.NodeTranslator):
    """Visit the full iterator IR tree, convert nodes to respective types and generate constraints."""

    def visit_SymRef(
        self, node: ir.SymRef, constraints: set[tuple[Type, Type]], symtypes: dict[str, Type]
    ) -> Type:
        if node.id in symtypes:
            res = symtypes[node.id]
            if isinstance(res, LetPolymorphic):
                return freshen(res.dtype)
            return res
        if node.id in BUILTIN_TYPES:
            return freshen(BUILTIN_TYPES[node.id])
        if node.id in (
            "make_tuple",
            "tuple_get",
            "shift",
            "cartesian_domain",
            "unstructured_domain",
        ):
            raise TypeError(
                f"Builtin '{node.id}' is only supported as applied/called function by the type checker"
            )
        if node.id in (ir.BUILTINS - ir.TYPEBUILTINS):
            raise NotImplementedError(f"Missing type definition for builtin '{node.id}'")

        return TypeVar.fresh()

    def visit_Literal(
        self, node: ir.Literal, constraints: set[tuple[Type, Type]], symtypes: dict[str, Type]
    ) -> Val:
        return Val(kind=Value(), dtype=Primitive(name=node.type))

    def visit_AxisLiteral(
        self,
        node: ir.AxisLiteral,
        constraints: set[tuple[Type, Type]],
        symtypes: dict[str, Type],
    ) -> Val:
        return Val(kind=Value(), dtype=AXIS_DTYPE, size=Scalar())

    def visit_OffsetLiteral(
        self,
        node: ir.OffsetLiteral,
        constraints: set[tuple[Type, Type]],
        symtypes: dict[str, Type],
    ) -> TypeVar:
        return TypeVar.fresh()

    def visit_Lambda(
        self, node: ir.Lambda, constraints: set[tuple[Type, Type]], symtypes: dict[str, Type]
    ) -> FunctionType:
        ptypes = {p.id: TypeVar.fresh() for p in node.params}
        ret = self.visit(node.expr, constraints=constraints, symtypes=symtypes | ptypes)
        return FunctionType(args=Tuple.from_elems(*(ptypes[p.id] for p in node.params)), ret=ret)

    def visit_FunCall(
        self, node: ir.FunCall, constraints: set[tuple[Type, Type]], symtypes: dict[str, Type]
    ) -> Type:
        if isinstance(node.fun, ir.SymRef):
            if node.fun.id == "make_tuple":
                # Calls to make_tuple are handled as being part of the grammar,
                # not as function calls
                argtypes = self.visit(node.args, constraints=constraints, symtypes=symtypes)
                kind = TypeVar.fresh()
                size = TypeVar.fresh()
                dtype = Tuple.from_elems(*(TypeVar.fresh() for _ in argtypes))
                for d, a in zip(dtype, argtypes):
                    constraints.add((Val(kind=kind, dtype=d, size=size), a))
                return Val(kind=kind, dtype=dtype, size=size)
            if node.fun.id == "tuple_get":
                # Calls to tuple_get are handled as being part of the grammar,
                # not as function calls
                if len(node.args) != 2:
                    raise TypeError("tuple_get requires exactly two arguments")
                if not isinstance(node.args[0], ir.Literal) or node.args[0].type != "int":
                    raise TypeError("The first argument to tuple_get must be a literal int")
                idx = int(node.args[0].value)
                tup = self.visit(node.args[1], constraints=constraints, symtypes=symtypes)
                kind = TypeVar.fresh()
                elem = TypeVar.fresh()
                size = TypeVar.fresh()

                dtype = Tuple(front=elem, others=TypeVar.fresh())
                for _ in range(idx):
                    dtype = Tuple(front=TypeVar.fresh(), others=dtype)

                val = Val(
                    kind=kind,
                    dtype=dtype,
                    size=size,
                )
                constraints.add((tup, val))
                return Val(kind=kind, dtype=elem, size=size)
            if node.fun.id == "shift":
                # Calls to shift are handled as being part of the grammar, not
                # as function calls; that is, the offsets are completely
                # ignored by the type inference algorithm
                it = Val(kind=Iterator())
                return FunctionType(
                    args=Tuple.from_elems(
                        it,
                    ),
                    ret=it,
                )
            if node.fun.id.endswith("domain"):
                for arg in node.args:
                    constraints.add(
                        (
                            Val(kind=Value(), dtype=NAMED_RANGE_DTYPE, size=Scalar()),
                            self.visit(arg, constraints=constraints, symtypes=symtypes),
                        )
                    )
                return Val(kind=Value(), dtype=DOMAIN_DTYPE, size=Scalar())

        fun = self.visit(node.fun, constraints=constraints, symtypes=symtypes)
        args = Tuple.from_elems(*self.visit(node.args, constraints=constraints, symtypes=symtypes))
        ret = TypeVar.fresh()
        constraints.add((fun, FunctionType(args=args, ret=ret)))
        return ret

    def visit_FunctionDefinition(
        self,
        node: ir.FunctionDefinition,
        constraints: set[tuple[Type, Type]],
        symtypes: dict[str, Type],
    ) -> FunctionDefinitionType:
        if node.id in symtypes:
            raise TypeError(f"Multiple definitions of symbol {node.id}")

        fun = self.visit(
            ir.Lambda(params=node.params, expr=node.expr),
            constraints=constraints,
            symtypes=symtypes,
        )
        constraints.add((fun, FunctionType()))
        return FunctionDefinitionType(name=node.id, fun=fun)

    def visit_StencilClosure(
        self,
        node: ir.StencilClosure,
        constraints: set[tuple[Type, Type]],
        symtypes: dict[str, Type],
    ) -> Closure:
        domain = self.visit(node.domain, constraints=constraints, symtypes=symtypes)
        stencil = self.visit(node.stencil, constraints=constraints, symtypes=symtypes)
        output = self.visit(node.output, constraints=constraints, symtypes=symtypes)
        inputs = Tuple.from_elems(
            *self.visit(node.inputs, constraints=constraints, symtypes=symtypes)
        )
        output_dtype = TypeVar.fresh()
        constraints.add((domain, Val(kind=Value(), dtype=Primitive(name="domain"), size=Scalar())))
        constraints.add((output, Val(kind=Iterator(), dtype=output_dtype, size=Column())))
        constraints.add(
            (
                stencil,
                FunctionType(args=inputs, ret=Val(kind=Value(), dtype=output_dtype, size=Column())),
            )
        )
        return Closure(output=output, inputs=inputs)

    def visit_FencilDefinition(
        self,
        node: ir.FencilDefinition,
        constraints: set[tuple[Type, Type]],
        symtypes: dict[str, Type],
    ) -> FencilDefinitionType:
        ftypes = []
        fmap = dict[str, LetPolymorphic]()
        # Note: functions have to be ordered according to Lisp/Scheme `let*`
        # statements; that is, functions can only reference other functions
        # that are defined before
        for f in node.function_definitions:
            c = set[tuple[Type, Type]]()
            ftype: FunctionDefinitionType = self.visit(f, constraints=c, symtypes=symtypes | fmap)
            ftype = typing.cast(FunctionDefinitionType, unify(ftype, c))
            ftypes.append(ftype)
            fmap[ftype.name] = LetPolymorphic(dtype=ftype.fun)

        params = {p.id: TypeVar.fresh() for p in node.params}
        self.visit(node.closures, constraints=constraints, symtypes=symtypes | fmap | params)
        return FencilDefinitionType(
            name=node.id,
            fundefs=Tuple.from_elems(*ftypes),
            params=Tuple.from_elems(*params.values()),
        )


def infer(expr: ir.Node, symtypes: typing.Optional[dict[str, Type]] = None) -> Type:
    """Infer the type of the given iterator IR expression."""
    if symtypes is None:
        symtypes = dict()

    # Collect constraints
    constraints = set[tuple[Type, Type]]()
    dtype = _TypeInferrer().visit(expr, constraints=constraints, symtypes=symtypes)
    # Compute the most general type that satisfies all constraints
    unified = unify(dtype, constraints)
    return reindex_vars(unified)


class PrettyPrinter(eve.NodeTranslator):
    """Pretty-printer for type expressions."""

    @staticmethod
    def _subscript(i: int) -> str:
        return "".join("₀₁₂₃₄₅₆₇₈₉"[int(d)] for d in str(i))

    @staticmethod
    def _superscript(i: int) -> str:
        return "".join("⁰¹²³⁴⁵⁶⁷⁸⁹"[int(d)] for d in str(i))

    def _fmt_size(self, size: Type) -> str:
        if size == Column():
            return "ᶜ"
        if size == Scalar():
            return "ˢ"
        assert isinstance(size, TypeVar)
        return self._superscript(size.idx)

    def _fmt_dtype(self, kind: Type, dtype_str: str) -> str:
        if kind == Value():
            return dtype_str
        if kind == Iterator():
            return "It[" + dtype_str + "]"
        assert isinstance(kind, TypeVar)
        return "ItOrVal" + self._subscript(kind.idx) + "[" + dtype_str + "]"

    def visit_EmptyTuple(self, node: EmptyTuple) -> str:
        return "()"

    def visit_Tuple(self, node: Tuple) -> str:
        s = "(" + self.visit(node.front)
        while isinstance(node.others, Tuple):
            node = node.others
            s += ", " + self.visit(node.front)
        s += ")"
        if not isinstance(node.others, EmptyTuple):
            s += ":" + self.visit(node.others)
        return s

    def visit_FunctionType(self, node: FunctionType) -> str:
        return self.visit(node.args) + " → " + self.visit(node.ret)

    def visit_Val(self, node: Val) -> str:
        return self._fmt_dtype(node.kind, self.visit(node.dtype) + self._fmt_size(node.size))

    def visit_Primitive(self, node: Primitive) -> str:
        return node.name

    def visit_FunctionDefinitionType(self, node: FunctionDefinitionType) -> str:
        return node.name + " :: " + self.visit(node.fun)

    def visit_Closure(self, node: Closure) -> str:
        return self.visit(node.inputs) + " ⇒ " + self.visit(node.output)

    def visit_FencilDefinitionType(self, node: FencilDefinitionType) -> str:
        assert isinstance(node.fundefs, (Tuple, EmptyTuple))
        assert isinstance(node.params, (Tuple, EmptyTuple))
        return (
            "{"
            + "".join(self.visit(f) + ", " for f in node.fundefs)
            + node.name
            + "("
            + ", ".join(self.visit(p) for p in node.params)
            + ")}"
        )

    def visit_ValTuple(self, node: ValTuple) -> str:
        if isinstance(node.dtypes, TypeVar):
            return (
                "("
                + self._fmt_dtype(node.kind, "T" + self._fmt_size(node.size))
                + ", …)"
                + self._subscript(node.dtypes.idx)
            )
        assert isinstance(node.dtypes, (Tuple, EmptyTuple))
        return (
            "("
            + ", ".join(
                self.visit(Val(kind=node.kind, dtype=dtype, size=node.size))
                for dtype in node.dtypes
            )
            + ")"
        )

    def visit_TypeVar(self, node: TypeVar) -> str:
        return "T" + self._subscript(node.idx)

    def visit_Type(self, node: Type) -> str:
        return (
            node.__class__.__name__
            + "("
            + ", ".join(f"{k}={v}" for k, v in node.iter_children_items())
            + ")"
        )


pformat = PrettyPrinter().visit


def pprint(x: Type) -> None:
    print(pformat(x))
