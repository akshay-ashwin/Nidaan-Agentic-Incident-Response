"""Wilson score interval for a binomial proportion."""
from __future__ import annotations

import math


def wilson(k: int, n: int, z: float = 1.96) -> dict | None:
    """95% Wilson CI by default. Returns None when n == 0."""
    if n <= 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return {"k": k, "n": n, "rate": p, "ci_low": max(0.0, centre - half), "ci_high": min(1.0, centre + half)}
