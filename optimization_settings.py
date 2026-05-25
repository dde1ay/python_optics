"""Backward-compatible merit-function helpers.

New code should import these from :mod:`periscopic.merit`.  This root-level
module is kept so older scripts that import ``optimization_settings`` continue
to work.
"""

from periscopic.merit import add_operand as _add_operand
from periscopic.merit import clear_merit_function


def add_merit_operand(mfe, zosapi, operand_name, target, weight=1.0):
    return _add_operand(mfe, zosapi, operand_name, target, weight)


__all__ = ["clear_merit_function", "add_merit_operand"]
