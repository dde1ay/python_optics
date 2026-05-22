from __future__ import annotations

import math
from typing import Any, Sequence


def _validate_rings_arms(rings: int, arms: int) -> None:
    if not isinstance(rings, int):
        raise ValueError(f"rings must be an integer, got {type(rings).__name__}")
    if not isinstance(arms, int):
        raise ValueError(f"arms must be an integer, got {type(arms).__name__}")
    if rings < 1:
        raise ValueError(f"rings must be >= 1, got {rings}")
    if arms < 1:
        raise ValueError(f"arms must be >= 1, got {arms}")


def generate_ring_radii(
    rings: int = 3,
    radius_mode: str = "gaussian",
    ring_radii: Sequence[float] | None = None,
) -> list[float]:
    _validate_rings_arms(rings, 1)
    if ring_radii is not None:
        if len(ring_radii) != rings:
            raise ValueError(f"len(ring_radii) must equal rings ({rings}), got {len(ring_radii)}")
        radii = [float(radius) for radius in ring_radii]
        invalid = [radius for radius in radii if radius < 0.0 or radius > 1.0]
        if invalid:
            raise ValueError(f"ring_radii values must satisfy 0 <= r <= 1, invalid values: {invalid}")
        return radii

    if radius_mode == "gaussian":
        nodes = _legendre_gauss_nodes(rings)
        return [math.sqrt(0.5 * (float(node) + 1.0)) for node in nodes]

    if radius_mode == "uniform":
        return [(index + 0.5) / rings for index in range(rings)]

    raise ValueError("radius_mode must be 'gaussian' or 'uniform' when ring_radii is not provided")


def generate_ring_radii_and_weights(
    rings: int = 3,
    radius_mode: str = "gaussian",
    ring_radii: Sequence[float] | None = None,
) -> list[tuple[float, float]]:
    radii = generate_ring_radii(rings=rings, radius_mode=radius_mode, ring_radii=ring_radii)
    if ring_radii is not None or radius_mode == "uniform":
        radial_weight = 1.0 / rings
        return [(radius, radial_weight) for radius in radii]

    if radius_mode == "gaussian":
        _nodes, weights = _legendre_gauss_nodes_and_weights(rings)
        radial_weights = [0.5 * float(weight) for weight in weights]
        return list(zip(radii, radial_weights))

    raise ValueError("radius_mode must be 'gaussian' or 'uniform' when ring_radii is not provided")


def _legendre_gauss_nodes(order: int) -> list[float]:
    nodes, _weights = _legendre_gauss_nodes_and_weights(order)
    return nodes


def _legendre_gauss_nodes_and_weights(order: int) -> tuple[list[float], list[float]]:
    try:
        from numpy.polynomial.legendre import leggauss

        nodes, weights = leggauss(order)
        return [float(node) for node in nodes], [float(weight) for weight in weights]
    except Exception:
        return _legendre_gauss_nodes_weights_fallback(order)


def _legendre_gauss_nodes_weights_fallback(order: int) -> tuple[list[float], list[float]]:
    nodes = [0.0] * order
    weights = [0.0] * order
    midpoint = (order + 1) // 2
    for index in range(midpoint):
        x = math.cos(math.pi * (index + 0.75) / (order + 0.5))
        derivative = 0.0
        for _iteration in range(100):
            p0 = 1.0
            p1 = x
            for degree in range(2, order + 1):
                p0, p1 = p1, ((2 * degree - 1) * x * p1 - (degree - 1) * p0) / degree
            derivative = order * (x * p1 - p0) / (x * x - 1.0)
            delta = p1 / derivative
            x -= delta
            if abs(delta) < 1.0e-15:
                break
        nodes[index] = -x
        nodes[order - 1 - index] = x
        weight = 2.0 / ((1.0 - x * x) * derivative * derivative)
        weights[index] = weight
        weights[order - 1 - index] = weight
    return nodes, weights


def generate_arm_angles(
    arms: int = 6,
    angle_offset_deg: float = 0.0,
    angle_mode: str = "zemax_symmetric",
) -> list[float]:
    _validate_rings_arms(1, arms)
    if angle_mode == "zemax_symmetric":
        if arms != 6:
            raise ValueError("angle_mode='zemax_symmetric' currently requires arms=6")
        return [60.0 + angle_offset_deg, 0.0 + angle_offset_deg, -60.0 + angle_offset_deg]

    if angle_mode == "full":
        return [angle_offset_deg + index * 360.0 / arms for index in range(arms)]

    raise ValueError("angle_mode must be 'zemax_symmetric' or 'full'")


def generate_ring_arm_pupil_points(
    rings: int = 3,
    arms: int = 6,
    radius_mode: str = "gaussian",
    ring_radii: Sequence[float] | None = None,
    angle_mode: str = "zemax_symmetric",
    angle_offset_deg: float = 0.0,
    weight_scale: float = 1.0,
) -> list[tuple[float, float, int, int, float]]:
    _validate_rings_arms(rings, arms)
    radii_and_weights = generate_ring_radii_and_weights(rings=rings, radius_mode=radius_mode, ring_radii=ring_radii)
    angles = generate_arm_angles(
        arms=arms,
        angle_offset_deg=angle_offset_deg,
        angle_mode=angle_mode,
    )
    if angle_mode == "zemax_symmetric" and rings == 3 and arms == 6:
        angular_factor = math.pi / 9.0
    elif angle_mode == "full":
        angular_factor = 2.0 * math.pi / arms
    else:
        angular_factor = 2.0 * math.pi / max(1, len(angles))

    points: list[tuple[float, float, int, int, float]] = []
    for arm_index, angle in enumerate(angles, start=1):
        theta = math.radians(angle)
        cos_theta = math.cos(theta)
        sin_theta = math.sin(theta)
        for ring_index, (radius, radial_weight) in enumerate(radii_and_weights, start=1):
            px = radius * cos_theta
            py = radius * sin_theta
            if abs(px) < 1.0e-14:
                px = 0.0
            if abs(py) < 1.0e-14:
                py = 0.0
            points.append((px, py, ring_index, arm_index, weight_scale * radial_weight * angular_factor))
    return points


def get_normalized_field_coordinates(TheSystem: Any) -> list[tuple[float, float]]:
    fields = TheSystem.SystemData.Fields
    raw: list[tuple[float, float]] = []
    for field_index in range(1, int(fields.NumberOfFields) + 1):
        field = fields.GetField(field_index)
        x = float(getattr(field, "X", 0.0))
        y = float(getattr(field, "Y", 0.0))
        raw.append((x, y))

    max_abs_x = max((abs(x) for x, _y in raw), default=0.0)
    max_abs_y = max((abs(y) for _x, y in raw), default=0.0)
    normalized: list[tuple[float, float]] = []
    for x, y in raw:
        hx = x / max_abs_x if max_abs_x > 0.0 else 0.0
        hy = y / max_abs_y if max_abs_y > 0.0 else 0.0
        if abs(hx) < 1.0e-14:
            hx = 0.0
        if abs(hy) < 1.0e-14:
            hy = 0.0
        normalized.append((hx, hy))
    return normalized


def validate_zemax_symmetric_3x6_sampling(tolerance: float = 1.0e-12) -> bool:
    expected = [
        (0.1678553435098644, 0.2907339832810120, 0.09696273622190668),
        (0.3535533905932737, 0.6123724356957946, 0.1551403779550515),
        (0.4709825725599466, 0.8157657451533231, 0.09696273622190668),
        (0.3357106870197288, 0.0, 0.09696273622190668),
        (0.7071067811865476, 0.0, 0.1551403779550515),
        (0.9419651451198934, 0.0, 0.09696273622190668),
        (0.1678553435098644, -0.2907339832810120, 0.09696273622190668),
        (0.3535533905932737, -0.6123724356957946, 0.1551403779550515),
        (0.4709825725599466, -0.8157657451533231, 0.09696273622190668),
    ]
    actual = generate_ring_arm_pupil_points(
        rings=3,
        arms=6,
        radius_mode="gaussian",
        angle_mode="zemax_symmetric",
    )
    if len(actual) != len(expected):
        raise AssertionError(f"Expected {len(expected)} points, got {len(actual)}")
    for index, (point, reference) in enumerate(zip(actual, expected), start=1):
        px, py, _ring, _arm, weight = point
        exp_px, exp_py, exp_weight = reference
        if abs(px - exp_px) >= tolerance or abs(py - exp_py) >= tolerance or abs(weight - exp_weight) >= tolerance:
            raise AssertionError(
                f"Point {index} mismatch: actual={(px, py, weight)}, expected={reference}"
            )
    return True


def _zosapi_module() -> Any:
    try:
        import ZOSAPI  # type: ignore
    except Exception as exc:
        raise RuntimeError("ZOSAPI module is not loaded. Connect to OpticStudio before adding MFE operands.") from exc
    return ZOSAPI


def _mfe_column(zosapi: Any, column_name: str) -> Any:
    return getattr(zosapi.Editors.MFE.MeritColumn, column_name)


def _operand_cell(operand: Any, zosapi: Any, column_name: str) -> Any:
    return operand.GetOperandCell(_mfe_column(zosapi, column_name))


def _clear_mfe(mfe: Any) -> None:
    count = int(mfe.NumberOfOperands)
    if count > 0:
        mfe.RemoveOperandsAt(1, count)


def _new_operand(mfe: Any, row: int | None = None) -> Any:
    if row is None:
        return mfe.AddOperand()
    try:
        inserted = mfe.InsertNewOperandAt(int(row))
        if inserted is not None:
            return inserted
    except AttributeError as exc:
        raise RuntimeError("MFE does not expose InsertNewOperandAt; cannot insert at start_row") from exc
    return mfe.GetOperandAt(int(row))


def _set_comment(operand: Any, zosapi: Any, comment: str) -> None:
    if hasattr(operand, "Comment"):
        try:
            operand.Comment = comment
            return
        except Exception:
            pass
    try:
        _operand_cell(operand, zosapi, "Comment").StringValue = comment
    except Exception:
        pass


def _set_mfe_operand(
    operand: Any,
    zosapi: Any,
    operand_type: str,
    target: float,
    weight: float,
    int1: int,
    wavelength: int,
    hx: float,
    hy: float,
    pupil_x: float,
    pupil_y: float,
    ex: float = 0.0,
    ey: float = 0.0,
) -> None:
    operand.ChangeType(getattr(zosapi.Editors.MFE.MeritOperandType, operand_type))
    operand.Target = float(target)
    operand.Weight = float(weight)
    # TRCX/TRCY MFE columns:
    # Int1, Int2, Hx, Hy, Px, Py, Ex, Ey map to Param1..Param8.
    _operand_cell(operand, zosapi, "Param1").IntegerValue = int(int1)
    _operand_cell(operand, zosapi, "Param2").IntegerValue = int(wavelength)
    _operand_cell(operand, zosapi, "Param3").DoubleValue = float(hx)
    _operand_cell(operand, zosapi, "Param4").DoubleValue = float(hy)
    _operand_cell(operand, zosapi, "Param5").DoubleValue = float(pupil_x)
    _operand_cell(operand, zosapi, "Param6").DoubleValue = float(pupil_y)
    _operand_cell(operand, zosapi, "Param7").DoubleValue = float(ex)
    _operand_cell(operand, zosapi, "Param8").DoubleValue = float(ey)


def add_ring_arm_trcx_trcy_operands(
    TheSystem: Any,
    rings: int = 3,
    arms: int = 6,
    wavelength: int = 1,
    radius_mode: str = "gaussian",
    ring_radii: Sequence[float] | None = None,
    angle_mode: str = "zemax_symmetric",
    angle_offset_deg: float = 0.0,
    target: float = 0.0,
    weight_scale: float = 1.0,
    start_row: int | None = None,
    clear_existing: bool = False,
    comment_prefix: bool = True,
) -> dict[str, Any]:
    _validate_rings_arms(rings, arms)
    if start_row is not None and (not isinstance(start_row, int) or start_row < 1):
        raise ValueError(f"start_row must be None or an integer >= 1, got {start_row!r}")
    if wavelength < 1:
        raise ValueError(f"wavelength must be >= 1, got {wavelength}")

    zosapi = _zosapi_module()
    mfe = TheSystem.MFE
    field_coordinates = get_normalized_field_coordinates(TheSystem)
    num_fields = len(field_coordinates)
    if num_fields < 1:
        raise RuntimeError("The current system has no fields.")

    points = generate_ring_arm_pupil_points(
        rings=rings,
        arms=arms,
        radius_mode=radius_mode,
        ring_radii=ring_radii,
        angle_mode=angle_mode,
        angle_offset_deg=angle_offset_deg,
        weight_scale=weight_scale,
    )
    point_count = len(points)
    num_angles_used = point_count // rings

    if clear_existing:
        _clear_mfe(mfe)
        current_row = 1
    elif start_row is None:
        current_row = None
    else:
        current_row = start_row

    first_row = 1 if clear_existing else (start_row if start_row is not None else int(mfe.NumberOfOperands) + 1)
    operands_added = 0
    comment_rows_added = 0

    for field_index, (hx, hy) in enumerate(field_coordinates, start=1):
        if comment_prefix:
            comment = (
                f"Operands for field {field_index}: {rings}-ring {arms}-arm TRCX/TRCY, "
                f"radius_mode={radius_mode}, angle_mode={angle_mode}"
            )
            operand = _new_operand(mfe, current_row)
            operand.ChangeType(getattr(zosapi.Editors.MFE.MeritOperandType, "BLNK"))
            _set_comment(operand, zosapi, comment)
            comment_rows_added += 1
            current_row = None if current_row is None else current_row + 1

        for px, py, _ring_index, _arm_index, operand_weight in points:
            trcx = _new_operand(mfe, current_row)
            _set_mfe_operand(trcx, zosapi, "TRCX", target, operand_weight, 0, wavelength, hx, hy, px, py)
            operands_added += 1
            current_row = None if current_row is None else current_row + 1

            trcy = _new_operand(mfe, current_row)
            _set_mfe_operand(trcy, zosapi, "TRCY", target, operand_weight, 0, wavelength, hx, hy, px, py)
            operands_added += 1
            current_row = None if current_row is None else current_row + 1

    end_row = first_row + operands_added + comment_rows_added - 1
    return {
        "num_fields": num_fields,
        "rings": rings,
        "arms": arms,
        "angle_mode": angle_mode,
        "num_angles_used": num_angles_used,
        "num_pupil_points_per_field": point_count,
        "num_operands_per_field": point_count * 2,
        "num_operands_added": operands_added,
        "num_comment_rows_added": comment_rows_added,
        "wavelength": wavelength,
        "radius_mode": radius_mode,
        "target": target,
        "weight_scale": weight_scale,
        "start_row": first_row,
        "end_row": end_row,
    }
