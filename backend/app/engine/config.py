"""Load and validate the scoring configuration."""
from __future__ import annotations

import copy
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "weights.yaml"
BAND_ORDER = ["low", "medium", "high", "critical"]


class ConfigError(ValueError):
    pass


def validate(cfg: dict[str, Any]) -> dict[str, Any]:
    for key in ("campus", "bands", "correlation", "login", "email"):
        if key not in cfg:
            raise ConfigError(f"missing section: {key}")
    # bands must tile 0..100 without gaps or overlap
    prev_hi = -1
    for name in BAND_ORDER:
        lo, hi = cfg["bands"][name]
        if lo != prev_hi + 1 or hi < lo:
            raise ConfigError(f"band {name} does not continue the previous band")
        prev_hi = hi
    if prev_hi != 100:
        raise ConfigError("bands must end at 100")
    for side in ("login", "email"):
        caps = cfg[side]["group_caps"]
        for name, sig in cfg[side]["signals"].items():
            if sig["group"] not in caps:
                raise ConfigError(f"{side}.{name}: group {sig['group']} has no cap")
            if sig["points"] < 0:
                raise ConfigError(f"{side}.{name}: negative points")
    for key in ("risky_tlds", "shorteners", "urgency_terms", "credential_terms", "injection_terms"):
        if not all(isinstance(x, str) for x in cfg["email"][key]):
            raise ConfigError(f"email.{key} must be a list of plain strings (quote entries that contain a colon)")
    for k in ("min_email_score", "min_login_score", "email_only_ceiling"):
        if k not in cfg["correlation"]:
            raise ConfigError(f"correlation.{k} is required")
    if not 0 <= cfg["correlation"]["uplift"] <= 1:
        raise ConfigError("correlation.uplift must be between 0 and 1")
    return cfg


def load(path: str | os.PathLike | None = None) -> dict[str, Any]:
    p = Path(path or os.environ.get("TRACEGUARD_WEIGHTS", DEFAULT_PATH))
    with open(p, "r", encoding="utf-8") as fh:
        return validate(yaml.safe_load(fh))


@lru_cache(maxsize=1)
def get() -> dict[str, Any]:
    return load()


def reload() -> dict[str, Any]:
    get.cache_clear()
    return get()


def with_overrides(cfg: dict[str, Any], **sections: Any) -> dict[str, Any]:
    out = copy.deepcopy(cfg)
    for k, v in sections.items():
        out[k] = v
    return out


def band_of(score: int, cfg: dict[str, Any]) -> str:
    for name in BAND_ORDER:
        lo, hi = cfg["bands"][name]
        if lo <= score <= hi:
            return name
    return "critical" if score > 100 else "low"


def band_rank(name: str) -> int:
    return BAND_ORDER.index(name)
