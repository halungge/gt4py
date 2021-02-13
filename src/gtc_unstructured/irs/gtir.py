# -*- coding: utf-8 -*-
#
# Eve Toolchain - GT4Py Project - GridTools Framework
#
# Copyright (c) 2020, CSCS - Swiss National Supercomputing Center, ETH Zurich
# All rights reserved.
#
# This file is part of the GT4Py project and the GridTools framework.
# GT4Py is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or any later
# version. See the LICENSE.txt file at the top-level directory of this
# distribution for a copy of the license or check <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import enum
from typing import List, Optional, Union

from devtools import debug  # noqa: F401
from pydantic import root_validator

from eve import Node, Str, StrEnum, SymbolTableTrait
from eve.type_definitions import SymbolName, SymbolRef
from gtc_unstructured.irs import common
from gtc import common as stable_gtc_common


class Expr(Node):
    location_type: common.LocationType
    pass


class Stmt(Node):
    location_type: common.LocationType
    pass


class Literal(common.Literal, Expr):
    pass


@enum.unique
class ReduceOperator(StrEnum):
    """Reduction operator identifier."""

    ADD = "ADD"
    MUL = "MUL"
    MAX = "MAX"
    MIN = "MIN"


class PrimaryLocation(Node):
    name: SymbolName
    location_type: common.LocationType


# TODO indirection not needed?
class ConnectivityRef(Node):
    name: SymbolRef


class LocationRef(Node):
    name: SymbolRef  # to PrimaryLocation or LocationComprehension


class LocationComprehension(Node):
    name: SymbolName
    of: ConnectivityRef


class NeighborReduce(Expr):
    operand: Expr
    op: ReduceOperator
    neighbors: LocationComprehension

    # TODO to validate we would need to lookup the connectivity,
    # i.e. can only be done when symbols are resolvable
    # @root_validator(pre=True)
    # def check_location_type(cls, values):
    #     if values["neighbors"].chain.elements[-1] != values["operand"].location_type:
    #         raise ValueError("Location type mismatch")
    #     return values


class FieldAccess(Expr):
    name: SymbolRef
    subscript: List[LocationRef]


# to SparseField (or TODO LocalField)
class NeighborAssignStmt(common.AssignStmt[FieldAccess, Expr], Stmt, SymbolTableTrait):
    neighbors: LocationComprehension


class AssignStmt(common.AssignStmt[FieldAccess, Expr], Stmt):
    pass


class BinaryOp(common.BinaryOp[Expr], Expr):
    pass


class VerticalDimension(Node):
    pass


class HorizontalDimension(Node):
    primary: common.LocationType


class Dimensions(Node):
    horizontal: Optional[HorizontalDimension]
    vertical: Optional[VerticalDimension]
    # other: TODO


class UField(Node):
    name: SymbolName
    vtype: common.DataType  # TODO rename vtype
    dimensions: Dimensions


class SparseField(Node):
    name: SymbolName
    connectivity: SymbolRef
    vtype: common.DataType  # TODO rename vtype
    dimensions: Dimensions


class TemporaryField(UField):
    pass


class HorizontalLoop(Node):
    stmt: Stmt
    location: PrimaryLocation

    @root_validator(pre=True)
    def check_location_type(cls, values):
        if values["stmt"].location_type != values["location"].location_type:
            raise ValueError("Location type mismatch")
        return values


class VerticalLoop(Node):
    # each statement inside a `with location_type` is interpreted as a full horizontal loop (see parallel model)
    horizontal_loops: List[HorizontalLoop]
    loop_order: common.LoopOrder


class Stencil(Node):
    vertical_loops: List[VerticalLoop]


class Connectivity(Node):
    name: SymbolName
    primary: common.LocationType
    secondary: common.LocationType
    max_neighbors: int
    has_skip_values: bool


class Computation(Node, SymbolTableTrait):
    name: Str
    connectivities: List[Connectivity]
    params: List[Union[UField, SparseField]]
    declarations: Optional[List[TemporaryField]]
    stencils: List[Stencil]

    _validate_symbol_refs = stable_gtc_common.validate_symbol_refs()
