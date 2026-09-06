"""Contact-wrench and external/internal-force decomposition.

For each hand, ``w_i`` is the sum of ``[f_c, (p_c-c_obj) x f_c]`` over its
contacts.  The Step 9 split is ``w_ext=w_L+w_R`` and
``w_int=(w_L-w_R)/2``.  A zero denominator is invalid and remains ``None``.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

import numpy as np

_EPS = 1e-15


def _vec3(value: Sequence[float], name: str) -> np.ndarray:
    try:
        array = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise TypeError("%s must be numeric" % name) from exc
    if array.shape != (3,):
        raise ValueError("%s must have shape (3,)" % name)
    if not np.all(np.isfinite(array)):
        raise ValueError("%s contains non-finite values" % name)
    return array


def _vec6(value: Sequence[float], name: str) -> np.ndarray:
    try:
        array = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise TypeError("%s must be numeric" % name) from exc
    if array.shape != (6,):
        raise ValueError("%s must have shape (6,)" % name)
    if not np.all(np.isfinite(array)):
        raise ValueError("%s contains non-finite values" % name)
    return array


def contact_wrench(force: Sequence[float], position: Sequence[float], object_center: Sequence[float]) -> np.ndarray:
    """Return one contact's six-vector ``[force, (position-center) x force]``."""
    vector = _vec3(force, "force")
    point = _vec3(position, "position")
    center = _vec3(object_center, "object_center")
    return np.concatenate((vector, np.cross(point - center, vector))).astype(np.float64, copy=False)


def _contact_field(contact: Any, names: Tuple[str, ...], label: str) -> Any:
    if isinstance(contact, Mapping):
        for name in names:
            if name in contact:
                return contact[name]
    else:
        for name in names:
            if hasattr(contact, name):
                return getattr(contact, name)
    raise KeyError("contact is missing %s" % label)


def sum_contact_wrenches(
    contacts: Iterable[Any],
    object_center: Sequence[float],
    vector_key: Optional[str] = None,
    position_key: Optional[str] = None,
) -> np.ndarray:
    """Sum force/contact-point or impulse/contact-point wrenches.

    ``impulse`` is accepted to match Stage 2E ``contact_wrench_by_side``.  Its
    units are preserved and are never relabelled as Newtons by this function.
    """
    center = _vec3(object_center, "object_center")
    result = np.zeros(6, dtype=np.float64)
    for contact in contacts:
        vector = _contact_field(contact, (vector_key,) if vector_key else ("force", "impulse", "vector"), "force or impulse")
        position = _contact_field(contact, (position_key,) if position_key else ("position", "point"), "position")
        result += contact_wrench(vector, position, center)
    return result


def _metadata(result: dict) -> dict:
    result.update({
        "norm_definition": "euclidean norm of 6D [force, torque] vector",
        "zero_denominator_valid": False,
        "units": "inherited from contact vector and position inputs",
    })
    return result


def side_wrench_from_record(record: Mapping[str, Any], vector_key: Optional[str] = None) -> np.ndarray:
    """Adapt one Stage 2E ``contact_wrench_by_side`` record to a 6D wrench.

    Stage 2E names the translational accumulation ``impulse`` and stores the
    accumulated moment as ``torque``.  The adapter preserves those units; it
    does not convert impulse to force without a timestep.
    """
    if not isinstance(record, Mapping):
        raise TypeError("side wrench record must be a mapping")
    key = vector_key
    if key is None:
        key = "force" if "force" in record else "impulse"
    if key not in record or "torque" not in record:
        raise KeyError("side wrench record needs %s and torque" % key)
    vector = _vec3(record[key], key)
    torque = _vec3(record["torque"], "torque")
    return np.concatenate((vector, torque)).astype(np.float64, copy=False)


def decompose_side_records(left_record: Mapping[str, Any], right_record: Mapping[str, Any], vector_key: Optional[str] = None) -> dict:
    """Decompose two Stage 2E side records without reinterpreting impulse units."""
    return decompose_wrenches(side_wrench_from_record(left_record, vector_key), side_wrench_from_record(right_record, vector_key))


def decompose_wrenches(left_wrench: Sequence[float], right_wrench: Sequence[float], epsilon: float = _EPS) -> dict:
    """Separate net/external and opposing/internal components for two hands."""
    left = _vec6(left_wrench, "left_wrench")
    right = _vec6(right_wrench, "right_wrench")
    external = left + right
    internal = 0.5 * (left - right)
    external_norm = float(np.linalg.norm(external))
    internal_norm = float(np.linalg.norm(internal))
    denominator = external_norm + internal_norm
    if not np.isfinite(denominator) or denominator <= float(epsilon):
        ratio, valid, reason = None, False, "zero external-plus-internal wrench denominator"
    else:
        ratio, valid, reason = float(internal_norm / denominator), True, "ok"
    return _metadata({
        "left_wrench": left, "right_wrench": right,
        "w_ext": external, "w_int": internal,
        "external_wrench": external, "internal_wrench": internal,
        "external_norm": external_norm, "internal_norm": internal_norm,
        "internal_fraction": ratio, "internal_ratio": ratio,
        "valid": valid, "validity_reason": reason,
    })


def decompose_contact_wrenches(
    left_contacts: Iterable[Any], right_contacts: Iterable[Any], object_center: Sequence[float],
    vector_key: Optional[str] = None, position_key: Optional[str] = None,
) -> dict:
    """Build per-hand contact wrenches and apply :func:`decompose_wrenches`."""
    left = sum_contact_wrenches(left_contacts, object_center, vector_key, position_key)
    right = sum_contact_wrenches(right_contacts, object_center, vector_key, position_key)
    result = decompose_wrenches(left, right)
    result.update({"left_contact_wrench": left, "right_contact_wrench": right})
    return result


def trajectory_wrench_decomposition(
    left_wrenches: Sequence[Sequence[float]], right_wrenches: Sequence[Sequence[float]], epsilon: float = _EPS,
) -> dict:
    """Apply the decomposition to every aligned timestep in two trajectories."""
    try:
        left = np.asarray(left_wrenches, dtype=np.float64)
        right = np.asarray(right_wrenches, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise TypeError("wrench trajectories must be numeric") from exc
    if left.ndim != 2 or right.ndim != 2 or left.shape != right.shape or left.shape[1:] != (6,):
        raise ValueError("wrench trajectories must both have shape (n, 6)")
    if not np.all(np.isfinite(left)) or not np.all(np.isfinite(right)):
        raise ValueError("wrench trajectories contain non-finite values")
    rows = [decompose_wrenches(a, b, epsilon) for a, b in zip(left, right)]
    fractions = np.asarray([np.nan if row["internal_fraction"] is None else row["internal_fraction"] for row in rows], dtype=np.float64)
    return {
        "left_wrench": np.ascontiguousarray(left), "right_wrench": np.ascontiguousarray(right),
        "w_ext": np.stack([row["w_ext"] for row in rows], axis=0),
        "w_int": np.stack([row["w_int"] for row in rows], axis=0),
        "internal_fraction": fractions,
        "valid": np.asarray([bool(row["valid"]) for row in rows], dtype=bool),
        "steps": rows, "units": "inherited from contact vector and position inputs",
    }


def delta_wrench_decomposition(
    baseline_left: Sequence[float], baseline_right: Sequence[float],
    modified_left: Sequence[float], modified_right: Sequence[float], epsilon: float = _EPS,
) -> dict:
    """Attribute a condition's wrench change to external versus internal change."""
    base_left, base_right = _vec6(baseline_left, "baseline_left"), _vec6(baseline_right, "baseline_right")
    new_left, new_right = _vec6(modified_left, "modified_left"), _vec6(modified_right, "modified_right")
    delta_left, delta_right = new_left - base_left, new_right - base_right
    delta_external, delta_internal = delta_left + delta_right, 0.5 * (delta_left - delta_right)
    external_norm, internal_norm = float(np.linalg.norm(delta_external)), float(np.linalg.norm(delta_internal))
    denominator = external_norm + internal_norm
    ratio = None if denominator <= float(epsilon) else float(internal_norm / denominator)
    return _metadata({
        "delta_left": delta_left, "delta_right": delta_right,
        "delta_w_ext": delta_external, "delta_w_int": delta_internal,
        "delta_external_norm": external_norm, "delta_internal_norm": internal_norm,
        "delta_internal_fraction": ratio, "valid": ratio is not None,
        "validity_reason": "ok" if ratio is not None else "zero delta external-plus-internal denominator",
    })


wrench_decomposition = decompose_wrenches
decompose_delta_wrenches = delta_wrench_decomposition
