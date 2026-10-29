"""Connector registry – resolves a connector address to an implementation.

The active backend is chosen by the ``TRACEGUARD_CONNECTOR`` environment
variable:

    TRACEGUARD_CONNECTOR=log    (default) – log-only, no external calls
    TRACEGUARD_CONNECTOR=m365           – Microsoft 365 via Graph API

The registry is a singleton initialised once at startup.  Connector objects
are shared across requests; implementations must be thread-safe (they should
hold no mutable request state).

Connector address routing
-------------------------
The ``connector`` field on an ``ActionRow`` is a dotted address such as
``mail.quarantine``, ``idp.revoke_sessions``, ``dns.block_domain``, or
``case.close``.  Addresses starting with ``case.`` or ``notify.`` are
handled internally by the workflow engine and are not dispatched to an
external connector backend.

For all other addresses the registry passes the call to the active backend
connector.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from . import BaseConnector, ConnectorResult
from .log_connector import LogConnector

log = logging.getLogger("traceguard.connector.registry")

# Addresses handled entirely inside the TraceGuard workflow engine.
# The registry returns a synthetic success result for these so the audit
# trail still records them without any external call.
_INTERNAL_PREFIXES = {"case.", "notify."}


def _is_internal(connector_address: str) -> bool:
    return any(connector_address.startswith(p) for p in _INTERNAL_PREFIXES)


class ConnectorRegistry:
    """Process-level singleton that dispatches approved actions to backends."""

    def __init__(self) -> None:
        self._backend: BaseConnector = self._load_backend()

    @staticmethod
    def _load_backend() -> BaseConnector:
        name = os.environ.get("TRACEGUARD_CONNECTOR", "log").strip().lower()
        if name == "log":
            log.info("Connector backend: log-only (TRACEGUARD_CONNECTOR=log)")
            return LogConnector()
        if name == "m365":
            from .m365 import M365Connector
            log.info("Connector backend: Microsoft 365 (TRACEGUARD_CONNECTOR=m365)")
            return M365Connector()
        log.warning("Unknown TRACEGUARD_CONNECTOR=%r; falling back to log-only", name)
        return LogConnector()

    @property
    def backend_name(self) -> str:
        return self._backend.name

    def dispatch(
        self,
        action_code: str,
        connector_address: str,
        context: dict[str, Any],
    ) -> ConnectorResult:
        """Route *action_code* to the appropriate backend.

        Internal connector addresses (``case.*``, ``notify.*``) are handled
        here without reaching the backend, so external connectors never need to
        know about them.

        Returns a :class:`~app.connectors.ConnectorResult` regardless of
        outcome; never raises.
        """
        ctx = {"connector": connector_address, **context}

        if _is_internal(connector_address):
            log.debug("Internal action %r (%r) – no external call", action_code, connector_address)
            return ConnectorResult(
                success=True,
                detail=f"Internal action '{action_code}' handled by TraceGuard workflow engine.",
                data={"internal": True, "connector": connector_address},
            )

        log.info(
            "Dispatching action=%r connector=%r backend=%r case_id=%s",
            action_code, connector_address, self._backend.name, context.get("case_id"),
        )
        try:
            result = self._backend.execute(action_code, ctx)
        except Exception as exc:
            # Belt-and-suspenders: implementations should not raise, but if
            # they do we catch here so the caller always gets a result.
            log.exception("Unexpected error in connector backend %r", self._backend.name)
            result = ConnectorResult(
                success=False,
                detail=f"Connector raised an unexpected error: {exc}",
                data={"error": str(exc), "connector": connector_address},
            )

        log.info(
            "Connector result: action=%r success=%s detail=%r",
            action_code, result.success, result.detail[:120],
        )
        return result


# Module-level singleton – import this from everywhere else.
registry: ConnectorRegistry | None = None


def get_registry() -> ConnectorRegistry:
    """Return the process-wide ConnectorRegistry, initialising it on first call."""
    global registry
    if registry is None:
        registry = ConnectorRegistry()
    return registry


def reset_registry() -> None:
    """Force re-initialisation on next :func:`get_registry` call.  Test use only."""
    global registry
    registry = None
