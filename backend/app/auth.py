"""TraceGuard authentication & authorisation.

Two modes, selected by the environment:

    TRACEGUARD_DEMO_AUTH=1  (default when unset)
        Header-based demo mode.  The React role-switcher sends
        X-Role / X-User / X-User-Id.  No cryptography.  Safe only
        behind a trusted reverse proxy or on localhost.

    TRACEGUARD_DEMO_AUTH=0
        OIDC / JWT mode (campus SSO style).
        The caller must send  Authorization: Bearer <id_token>.
        Required env vars:
            TRACEGUARD_OIDC_ISSUER   – e.g. https://sso.kestrel.edu
            TRACEGUARD_OIDC_AUDIENCE – the client-id / resource-indicator
        Optional:
            TRACEGUARD_OIDC_JWKS_URL – override JWKS endpoint (default: {issuer}/.well-known/jwks.json)
            TRACEGUARD_OIDC_ROLE_CLAIM – claim that carries the role (default: "traceguard_role")
            TRACEGUARD_OIDC_SUB_CLAIM  – claim used as user_id (default: "sub")

        Roles are read from the JWT claim named by TRACEGUARD_OIDC_ROLE_CLAIM.
        Expected values: "admin" | "analyst" | "user".
        Anything else is mapped to "user".

Role permissions
----------------
admin   – everything
analyst – read any case/login; approve actions; cannot change settings or load batches
user    – /api/me/* only; can only read their own alerts / case data
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# ---------------------------------------------------------------------------
# Shared Actor dataclass
# ---------------------------------------------------------------------------

VALID_ROLES = {"admin", "analyst", "user"}

_DEMO_MODE: bool = os.environ.get("TRACEGUARD_DEMO_AUTH", "1").strip() not in ("0", "false", "no")


@dataclass
class Actor:
    name: str
    role: str
    user_id: str = ""
    email: str = ""
    claims: dict = field(default_factory=dict)

    def is_admin(self) -> bool:
        return self.role == "admin"

    def is_staff(self) -> bool:
        return self.role in {"admin", "analyst"}

    def owns(self, user_id: str) -> bool:
        """True when this actor IS the target user or is staff."""
        return self.is_staff() or self.user_id == user_id


# ---------------------------------------------------------------------------
# Demo-mode dependency (header-based, matches old behaviour exactly)
# ---------------------------------------------------------------------------

def _demo_actor(
    x_role: str = Header("analyst"),
    x_user: str = Header("Demo Analyst"),
    x_user_id: str = Header(""),
) -> Actor:
    role = x_role.lower()
    if role not in VALID_ROLES:
        raise HTTPException(400, f"unknown role '{role}' – must be one of {sorted(VALID_ROLES)}")
    return Actor(name=x_user, role=role, user_id=x_user_id)


# ---------------------------------------------------------------------------
# OIDC / JWT mode
# ---------------------------------------------------------------------------

_bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def _jwks_client():
    """Return a PyJWT JWKSClient (cached for the process lifetime)."""
    try:
        import jwt.algorithms  # noqa: F401
        from jwt import PyJWKClient
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "PyJWT with cryptography is required for OIDC mode. "
            "pip install 'PyJWT[crypto]'"
        ) from exc

    issuer = os.environ.get("TRACEGUARD_OIDC_ISSUER", "").rstrip("/")
    jwks_url = os.environ.get(
        "TRACEGUARD_OIDC_JWKS_URL",
        f"{issuer}/.well-known/jwks.json",
    )
    return PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)


def _oidc_actor(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Actor:
    import jwt as pyjwt

    if credentials is None:
        raise HTTPException(401, "Authorization header missing (Bearer token required)")

    token = credentials.credentials
    issuer = os.environ.get("TRACEGUARD_OIDC_ISSUER", "").rstrip("/")
    audience = os.environ.get("TRACEGUARD_OIDC_AUDIENCE", "")
    role_claim = os.environ.get("TRACEGUARD_OIDC_ROLE_CLAIM", "traceguard_role")
    sub_claim = os.environ.get("TRACEGUARD_OIDC_SUB_CLAIM", "sub")

    if not issuer:
        raise RuntimeError("TRACEGUARD_OIDC_ISSUER is not set")

    try:
        client = _jwks_client()
        signing_key = client.get_signing_key_from_jwt(token)
        claims = pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=audience or None,
            issuer=issuer,
            options={"require": ["exp", "sub"]},
        )
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(401, "Token has expired")
    except pyjwt.InvalidTokenError as exc:
        raise HTTPException(401, f"Invalid token: {exc}")

    raw_role = str(claims.get(role_claim, "user")).lower()
    role = raw_role if raw_role in VALID_ROLES else "user"
    user_id = str(claims.get(sub_claim, ""))
    name = claims.get("name") or claims.get("preferred_username") or user_id
    email = claims.get("email", "")

    return Actor(name=name, role=role, user_id=user_id, email=email, claims=claims)


# ---------------------------------------------------------------------------
# Public dependency – automatically picks the right backend
# ---------------------------------------------------------------------------

def get_actor(
    request: Request,
    x_role: str = Header("analyst"),
    x_user: str = Header("Demo Analyst"),
    x_user_id: str = Header(""),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Actor:
    if _DEMO_MODE:
        return _demo_actor(x_role=x_role, x_user=x_user, x_user_id=x_user_id)
    return _oidc_actor(credentials=credentials)


# ---------------------------------------------------------------------------
# Role-enforcing dependencies
# ---------------------------------------------------------------------------

def require_actor(a: Actor = Depends(get_actor)) -> Actor:
    """Any authenticated principal."""
    return a


def require_staff(a: Actor = Depends(get_actor)) -> Actor:
    """Analyst or admin."""
    if not a.is_staff():
        raise HTTPException(403, "analyst or admin role required")
    return a


def require_admin(a: Actor = Depends(get_actor)) -> Actor:
    """Admin only."""
    if not a.is_admin():
        raise HTTPException(403, "admin role required")
    return a


def require_analyst(a: Actor = Depends(get_actor)) -> Actor:
    """Analyst only (not admin, not plain user)."""
    if a.role != "analyst":
        raise HTTPException(403, "analyst role required")
    return a


# ---------------------------------------------------------------------------
# Utility – per-user data isolation
# ---------------------------------------------------------------------------

def assert_owns(actor: Actor, target_user_id: str) -> None:
    """Raise 403 if *actor* is not staff and does not own *target_user_id*."""
    if not actor.owns(target_user_id):
        raise HTTPException(403, "you may only access your own data")
