# GT4Py Project - GridTools Framework
#
# Copyright (c) 2014-2022, ETH Zurich
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


from typing import Callable

from functional.fencil_processors import defs as defs
from functional.fencil_processors.callables.cache import Strategy as CacheStrategy, get_cache_folder
from functional.fencil_processors.callables.importer import import_callables

from . import bindings, build


def create_callable(
    source_module: defs.SourceCodeModule, cache_strategy=CacheStrategy.SESSION
) -> Callable:
    cache_folder = get_cache_folder(
        source_module.entry_point.name, source_module.source_code, cache_strategy
    )
    module_file = build.CMakeProject.get_binary(cache_folder, source_module.entry_point.name)
    try:
        return import_callables(module_file)[source_module.entry_point.name]
    except ModuleNotFoundError:
        pass

    src_header_file = source_module.entry_point.name + ".cpp.inc"
    bindings_file = source_module.entry_point.name + "_bindings.cpp"
    bindings_module = bindings.create_bindings(source_module.entry_point, src_header_file)

    deps = [*source_module.library_deps, *bindings_module.library_deps]
    sources = {
        src_header_file: source_module.source_code,
        bindings_file: bindings_module.source_code,
    }
    project = build.CMakeProject(
        name=source_module.entry_point.name, dependencies=deps, sources=sources
    )

    project.write(cache_folder)
    project.configure()
    project.build()

    return import_callables(module_file)[source_module.entry_point.name]
