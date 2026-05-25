"""Periscopic lens staged optimization workflow package.

Public entry points are exported here so scripts can import from
``periscopic`` without reaching into individual modules unless they need a
lower-level helper.
"""

from .config import PeriscopicConfig
from .connection import ZemaxConnection, connect_opticstudio
from .workflow import run_workflow

__all__ = [
    "PeriscopicConfig",
    "ZemaxConnection",
    "connect_opticstudio",
    "run_workflow",
]
