"""Log-only connector – the safe default.

Writes a structured log entry and returns success.  Behaviour is identical to
the hard-coded ``"Reversible step run automatically (log-only connector in
this build)."`` note that existed before the connector system was introduced,
so all existing tests and the demo continue to work without any configuration.

No external calls are made; this connector is always retry-safe.
"""
from __future__ import annotations

import logging
from typing import Any

from . import BaseConnector, ConnectorResult

log = logging.getLogger("traceguard.connector.log")


class LogConnector(BaseConnector):
    """Write a log entry; pretend the action succeeded."""

    name = "log"

    def execute(self, action_code: str, context: dict[str, Any]) -> ConnectorResult:
        msg = (
            f"[LOG-ONLY] action={action_code!r} connector={context.get('connector')!r} "
            f"case_id={context.get('case_id')} user_id={context.get('user_id')!r}"
        )
        log.info(msg)
        return ConnectorResult(
            success=True,
            detail=f"Log-only connector: action '{action_code}' recorded but no external system was called.",
            data={"logged": True},
        )
