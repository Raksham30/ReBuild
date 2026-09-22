"""
FastAPI dependency that resolves the current user's uid from the
Authorization header.

Real mode:  Authorization: Bearer <Firebase ID token>, verified via the
            Firebase Admin SDK against the service account configured in
            FIREBASE_SERVICE_ACCOUNT_PATH. Works for any Firebase Auth
            sign-in method (Google, email/password, etc.) -- the token
            shape is the same regardless of how the user signed in.
Dev mode:   (no FIREBASE_SERVICE_ACCOUNT_PATH configured) the bearer
            token is treated literally as the uid -- lets you develop
            and test multi-user/multi-workspace logic locally without a
            real Firebase project. NEVER safe outside local development.

Deliberately not an Azure service: end-user auth lives on Firebase while
storage/search/models/orchestration stay on Azure. Every other module in
this app only depends on get_current_uid returning a string -- it has no
idea which identity provider produced it.
"""
from __future__ import annotations
from fastapi import Header, HTTPException
from app.config import get_settings

_firebase_app = None


def _get_firebase_app():
    global _firebase_app
    if _firebase_app is None:
        import os
        import firebase_admin
        from firebase_admin import credentials
        settings = get_settings()

        path = settings.firebase_service_account_path
        resolved = os.path.abspath(path)
        if not os.path.isfile(resolved):
            # A missing service-account file is a SERVER misconfiguration,
            # not something wrong with the caller's token -- raise it here,
            # distinctly, with enough info to actually fix it, instead of
            # letting it fall through to get_current_uid's generic
            # "Invalid Firebase token" 401 (which wrongly implies the
            # problem is the user's login, not the server's file path).
            raise RuntimeError(
                f"FIREBASE_SERVICE_ACCOUNT_PATH is set to {path!r} but no file exists "
                f"there. Resolved to: {resolved!r} (cwd: {os.getcwd()!r}). "
                f"If FIREBASE_SERVICE_ACCOUNT_PATH is a relative path, it resolves "
                f"against wherever uvicorn was launched from -- either run uvicorn "
                f"from inside backend/, or set an absolute path in backend/.env."
            )
        try:
            import json
            with open(resolved, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "private_key" in data and isinstance(data["private_key"], str):
                data["private_key"] = data["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(data)
            _firebase_app = firebase_admin.initialize_app(cred)
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize Firebase Admin SDK from {resolved!r}: {e}"
            )
    return _firebase_app


def get_current_uid(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing 'Authorization: Bearer <token>' header")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(401, "Empty bearer token")

    settings = get_settings()
    if not settings.use_firebase:
        return token  # DEV MODE

    # Config problems (missing/invalid service account file) are a server
    # error (500) -- distinct from a bad/expired token (401) below.
    try:
        _get_firebase_app()
    except RuntimeError as e:
        raise HTTPException(500, str(e))

    from firebase_admin import auth as firebase_auth
    try:
        # clock_skew_seconds: a PC clock a second or two behind Google's makes freshly
        # issued tokens fail with "Token used too early" (a random 401 that goes
        # away on retry). Allow up to 60s of skew.
        decoded = firebase_auth.verify_id_token(token, clock_skew_seconds=60)
    except Exception as e:
        raise HTTPException(401, f"Invalid Firebase token: {e}")

    uid = decoded.get("uid")
    if not uid:
        raise HTTPException(401, "Token missing uid claim")
    return uid
