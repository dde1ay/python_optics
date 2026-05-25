"""Backward-compatible system and solve helpers.

New periscopic workflow code keeps system construction helpers in
``periscopic.lens_builder`` and solve helpers in ``periscopic.solves``.  This
root-level module preserves the old function names for scripts that still
import ``system_settings``.
"""

from periscopic.lens_builder import (
    ensure_surface_count,
    first_existing_attr,
    make_surface_stop,
    set_angle_fields,
    set_aperture_to_paraxial_working_f_number,
    set_first_available_material,
    set_primary_wavelength,
)
from periscopic.solves import (
    _set_first_existing,
    _solve_settings,
    set_radius_variable,
    set_surface_pickup,
    set_thickness_marginal_ray_height,
    set_thickness_variable,
)


def make_radius_variable(surface):
    return set_radius_variable(surface)


def make_thickness_variable(surface):
    return set_thickness_variable(surface)


def make_thickness_marginal_ray_height(surface, zosapi):
    return set_thickness_marginal_ray_height(surface, zosapi)


def get_solve_settings(solve_data, primary_name, aliases=None):
    return _solve_settings(solve_data, primary_name, tuple(aliases or ()))


def set_existing_solve_value(settings, names, value):
    return _set_first_existing(settings, tuple(names), value)


def make_surface_pickup(cell, zosapi, pickup_surface, scale=1.0, offset=0.0, column=None):
    return set_surface_pickup(cell, zosapi, pickup_surface, scale, offset, column)


__all__ = [
    "ensure_surface_count",
    "first_existing_attr",
    "get_solve_settings",
    "make_radius_variable",
    "make_surface_pickup",
    "make_surface_stop",
    "make_thickness_marginal_ray_height",
    "make_thickness_variable",
    "set_angle_fields",
    "set_aperture_to_paraxial_working_f_number",
    "set_existing_solve_value",
    "set_first_available_material",
    "set_primary_wavelength",
]
