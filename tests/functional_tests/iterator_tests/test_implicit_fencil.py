import numpy as np
import pytest

from functional.iterator.builtins import *
from functional.iterator.embedded import np_as_located_field
from functional.iterator.runtime import CartesianAxis, fundef

from .conftest import run_processor


I = CartesianAxis("I")

_isize = 10


@pytest.fixture
def dom():
    return {I: range(_isize)}


def a_field():
    return np_as_located_field(I)(np.asarray(range(_isize)))


def out_field():
    return np_as_located_field(I)(np.zeros(shape=(_isize,)))


@fundef
def copy_stencil(inp):
    return deref(inp)


def test_single_argument(program_processor, dom):
    program_processor, validate = program_processor

    inp = a_field()
    out = out_field()

    run_processor(copy_stencil[dom], program_processor, inp, out=out, offset_provider={})
    if validate:
        assert np.allclose(inp, out)


def test_2_arguments(program_processor, dom):
    program_processor, validate = program_processor

    @fundef
    def fun(inp0, inp1):
        return deref(inp0) + deref(inp1)

    inp0 = a_field()
    inp1 = a_field()
    out = out_field()

    run_processor(fun[dom], program_processor, inp0, inp1, out=out, offset_provider={})

    if validate:
        assert np.allclose(inp0.array() + inp1.array(), out)


def test_lambda_domain(program_processor):
    program_processor, validate = program_processor
    inp = a_field()
    out = out_field()

    dom = lambda: cartesian_domain(named_range(I, 0, 10))
    run_processor(copy_stencil[dom], program_processor, inp, out=out, offset_provider={})

    if validate:
        assert np.allclose(inp, out)
