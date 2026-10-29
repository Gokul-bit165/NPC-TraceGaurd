"""Connector interface for TraceGuard response actions.

A *connector* is the bridge between an approved TraceGuard action and the
external system that carries it out (Microsoft 365, Google Workspace, DNS
filter, …).

Every connector must implement :class:`BaseConnector`.  The active connector
for a given ``connector`` code is resolved at runtime by
:mod:`app.connectors.registry`.

Two implementations are always present:

* :class:`~app.connectors.log_connector.LogConnector` – the default.  Writes a
  detailed log entry and returns success.  Behaviour is identical to the
  previous hard-coded log-only approach, so existing tests and demo mode are
  completely unaffected.

* :class:`~app.connectors.m365.M365Connector` – Microsoft 365 via the Graph
  API.  Activated when ``TRACEGUARD_CONNECTOR=m365`` and the required OAuth
  env vars are present.  See :mod:`app.connectors.m365` for the full env-var
  reference.

Retry-safety contract
---------------------
Every ``execute()`` implementation MUST be idempotent: calling it twice with
the same arguments must produce the same observable outcome and must not
return an error on the second call when the first already succeeded.  The
registry calls ``execute()`` exactly once per approval, but network retries
may replay the call.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ConnectorResult:
    """Outcome returned by :meth:`BaseConnector.execute`.

    Attributes
    ----------
    success:
        ``True`` when the external system confirmed the action.
    detail:
        Human-readable description stored verbatim in the audit trail.
    data:
        Any JSON-serialisable payload returned by the external API (IDs,
        timestamps, …).  Stored alongside *detail* in the audit row.
    """

    success: bool
    detail: str
    data: dict[str, Any] | None = None


class BaseConnector(ABC):
    """Abstract base that every connector implementation must subclass."""

    # Short name used in log messages and the audit trail.
    name: str = "base"

    @abstractmethod
    def execute(self, action_code: str, context: dict[str, Any]) -> ConnectorResult:
        """Carry out *action_code* using *context*.

        Parameters
        ----------
        action_code:
            The ``ActionRow.code`` value, e.g. ``"quarantine_message"``.
        context:
            A dict built from the ``ActionRow`` and its parent ``CaseRow``.
            Guaranteed keys: ``case_id``, ``user_id``, ``action_id``,
            ``connector`` (the dotted connector address, e.g. ``"mail.quarantine"``).
            Optional keys supplied when available: ``email_id``, ``sender``,
            ``subject``, ``message_id`` (RFC-2822 Message-ID), ``links``,
            ``top_email_id``, ``campaign_key``.
        """
