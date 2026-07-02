"""Typed errors for the equip eval/benchmark stage."""

from __future__ import annotations

from ..errors import EquipError


class EvalError(EquipError):
    """Base for every eval-stage failure the CLI maps to an exit code."""


class EvalSuiteError(EvalError):
    """The eval suite content is malformed (bad JSON / shape / duplicate ``case_id``)."""


class ObservationsError(EvalError):
    """The observations content is malformed (bad JSON / shape)."""


class EvalSuiteNotFoundError(EvalError):
    """The expected ``<tool>.suite.json`` does not exist (CLI maps to exit 2)."""


class ObservationMismatchError(EvalError):
    """An observation's ``case_id`` is not present in the suite."""


class MissingObservationError(EvalError):
    """A suite case has no matching observation."""
