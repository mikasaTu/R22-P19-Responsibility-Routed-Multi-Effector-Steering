from __future__ import annotations


def _label(value):
    return str(value).replace(".", "p")


def single_factor_conditions():
    values = {
        "receiver_gain": [0.7, 0.5, 0.35],
        "receiver_delay_steps": [4, 8, 12],
        "receiver_friction_scale": [0.7, 0.5, 0.3],
        "object_com_shift_mm": [15, 30],
        "receiver_grasp_offset_mm": [5, 10],
    }
    rows = [{"name": "clean", "parameters": {}}]
    for key, levels in values.items():
        rows.extend({"name": f"{key}_{_label(value)}", "parameters": {key: value}}
                    for value in levels)
    assert len(rows) == 14 and len({row["name"] for row in rows}) == 14
    return rows


def two_factor_conditions():
    values = [
        {"receiver_gain": 0.5, "receiver_delay_steps": 8},
        {"receiver_gain": 0.35, "receiver_friction_scale": 0.5},
        {"receiver_delay_steps": 8, "receiver_friction_scale": 0.5},
        {"receiver_gain": 0.5, "object_com_shift_mm": 30},
        {"receiver_friction_scale": 0.5, "receiver_grasp_offset_mm": 10},
        {"object_com_shift_mm": 30, "receiver_grasp_offset_mm": 10},
    ]
    return [{"name": f"two_factor_{i:02d}", "parameters": value}
            for i, value in enumerate(values, 1)]
