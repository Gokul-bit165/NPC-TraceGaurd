"""Shared scoring helpers: group caps and side totals. Points are integers so the ledger sums exactly."""
from __future__ import annotations

from .types import Evidence


def rnd(x: float) -> int:
    """Round half up (Python's round() is banker's rounding, which surprises people reading a ledger)."""
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


def make(code: str, side: str, label: str, detail: str, points: float, group: str, ref: str | None = None) -> Evidence:
    p = rnd(points)
    return Evidence(code=code, side=side, label=label, detail=detail, points=p, raw_points=p, group=group, ref=ref)


def apply_group_caps(items: list[Evidence], caps: dict[str, int]) -> list[Evidence]:
    """Largest signals in each group are awarded first; once a group is at its cap the rest score 0.

    This stops several correlated signals (new country + new city + new IP) from counting the same
    underlying fact three times. The raw points stay on the line so the analyst can see what was capped.
    """
    remaining = dict(caps)
    for e in sorted(items, key=lambda x: -x.raw_points):
        cap = remaining.get(e.group, 10 ** 9)
        e.points = min(e.raw_points, cap)
        remaining[e.group] = cap - e.points
    return sorted(items, key=lambda x: (-x.points, x.code))


def side_total(items: list[Evidence], side: str, ceiling: int = 100) -> tuple[int, list[Evidence]]:
    """Return the side score (0..ceiling) and the ledger lines, adding a negative CAP line if clipped."""
    total = sum(e.points for e in items)
    lines = list(items)
    if total > ceiling:
        lines.append(Evidence(
            code=f"{side.upper()}_CAP", side="cap", label=f"{side.title()} score capped at {ceiling}",
            detail=f"Signals added up to {total}; the {side} score cannot exceed {ceiling}.",
            points=ceiling - total, raw_points=ceiling - total, group="cap"))
        total = ceiling
    return total, lines
