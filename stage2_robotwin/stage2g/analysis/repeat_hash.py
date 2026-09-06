"""Bitwise repeat checks for frozen effect vectors."""
from __future__ import annotations

import hashlib
import struct
from typing import Any, Mapping, Sequence

import numpy as np


def canonical_effect_vector_bytes(values: Sequence[float]) -> bytes:
    """Encode shape and exact little-endian float64 bytes; reject non-finite data."""
    try:
        array = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise TypeError("effect vector must be numeric") from exc
    if array.ndim == 0:
        array = array.reshape(1)
    if not np.all(np.isfinite(array)):
        raise ValueError("effect vector contains non-finite values")
    array = np.ascontiguousarray(array, dtype=np.dtype("<f8"))
    payload = bytearray(b"r22p19.stage2g.effect-vector.v1\0")
    payload.extend(struct.pack("<I", int(array.ndim)))
    for size in array.shape:
        payload.extend(struct.pack("<Q", int(size)))
    payload.extend(array.tobytes(order="C"))
    return bytes(payload)


def effect_vector_sha256(values: Sequence[float]) -> str:
    """Hash the exact canonical effect-vector representation."""
    return hashlib.sha256(canonical_effect_vector_bytes(values)).hexdigest()


def effect_vectors_bitwise_equal(left: Sequence[float], right: Sequence[float]) -> bool:
    """Return true only when shape and every encoded IEEE-754 byte agree."""
    try:
        return canonical_effect_vector_bytes(left) == canonical_effect_vector_bytes(right)
    except (TypeError, ValueError):
        return False


def compare_effect_vectors(left: Sequence[float], right: Sequence[float]) -> dict:
    """Return hashes and an explicit bitwise-equality decision for two repeats."""
    left_hash = effect_vector_sha256(left)
    right_hash = effect_vector_sha256(right)
    return {
        "bitwise_equal": bool(left_hash == right_hash),
        "left_sha256": left_hash,
        "right_sha256": right_hash,
        "hash_algorithm": "sha256(canonical little-endian float64 bytes + shape)",
    }


def assert_repeat_effect_vectors(left: Sequence[float], right: Sequence[float]) -> dict:
    comparison = compare_effect_vectors(left, right)
    if not comparison["bitwise_equal"]:
        raise AssertionError(
            "repeat effect vectors differ: %s != %s"
            % (comparison["left_sha256"], comparison["right_sha256"])
        )
    return comparison


def compare_repeat_cells(first: Mapping[str, Any], second: Mapping[str, Any], effect_key: str = "effect_vector") -> dict:
    """Compare two cell records using their raw effect-vector payloads."""
    if effect_key not in first or effect_key not in second:
        raise KeyError("both repeat cells must contain %s" % effect_key)
    result = compare_effect_vectors(first[effect_key], second[effect_key])
    result["effect_key"] = effect_key
    return result


# Match the Stage 2F helper name so reports can use one spelling across stages.
canonical_effect_sha256 = effect_vector_sha256
