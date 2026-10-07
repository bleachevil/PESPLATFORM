"""Google OAuth for the website and a later manager app."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "data" / "google_oauth.env"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
SCOPES = "openid email profile"
GOOGLE_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}


def _parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_google_config() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV_PATH.exists():
        values.update(_parse_env(ENV_PATH.read_text(encoding="utf-8")))
    client_id = os.environ.get("GOOGLE_CLIENT_ID") or values.get("GOOGLE_CLIENT_ID") or ""
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET") or values.get("GOOGLE_CLIENT_SECRET") or ""
    extra = os.environ.get("GOOGLE_APP_CLIENT_IDS") or values.get("GOOGLE_APP_CLIENT_IDS") or ""
    return {
        "client_id": client_id.strip(),
        "client_secret": client_secret.strip(),
        "app_client_ids": extra.strip(),
    }


def allowed_audiences() -> list[str]:
    config = load_google_config()
    audiences = [config["client_id"]] if config["client_id"] else []
    audiences.extend(part.strip() for part in config["app_client_ids"].split(",") if part.strip())
    return audiences


def google_configured() -> bool:
    config = load_google_config()
    return bool(config["client_id"] and config["client_secret"])


def save_google_config(client_id: str, client_secret: str) -> None:
    client_id = (client_id or "").strip()
    client_secret = (client_secret or "").strip()
    if not client_id or not client_secret:
        raise ValueError("Client ID and Client secret are required")
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    ENV_PATH.write_text(
        f"GOOGLE_CLIENT_ID={client_id}\nGOOGLE_CLIENT_SECRET={client_secret}\n",
        encoding="utf-8",
    )


def pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    return verifier, challenge


def google_authorize_url(redirect_uri: str, state: str, code_challenge: str = "") -> str:
    config = load_google_config()
    if not config["client_id"]:
        raise ValueError("Google sign-in is not connected on this server")
    params = {
        "client_id": config["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
        "include_granted_scopes": "true",
    }
    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"
    return AUTH_URL + "?" + urlencode(params)


def _request_json(url: str, data: dict[str, str] | None = None, token: str = "") -> dict:
    body = urlencode(data).encode("utf-8") if data is not None else None
    request = Request(url, data=body, method="POST" if data is not None else "GET")
    if data is not None:
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"Google OAuth failed: {detail}") from exc
    except URLError as exc:
        raise ValueError(f"Could not reach Google: {exc.reason}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Google returned an unexpected response")
    return payload


def _profile_from_payload(payload: dict) -> dict:
    return {
        "sub": str(payload.get("sub") or payload.get("id") or ""),
        "email": str(payload.get("email") or ""),
        "name": str(payload.get("name") or payload.get("given_name") or ""),
    }


def exchange_google_code(code: str, redirect_uri: str, code_verifier: str = "") -> dict:
    config = load_google_config()
    data = {
        "code": code,
        "client_id": config["client_id"],
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    if config["client_secret"]:
        data["client_secret"] = config["client_secret"]
    if code_verifier:
        data["code_verifier"] = code_verifier
    tokens = _request_json(TOKEN_URL, data)
    access_token = tokens.get("access_token")
    id_token = tokens.get("id_token")
    if id_token:
        return verify_google_id_token(str(id_token))
    if not access_token:
        raise ValueError("Google did not return an access token")
    return _profile_from_payload(_request_json(USERINFO_URL, token=str(access_token)))


def verify_google_id_token(id_token: str) -> dict:
    payload = _request_json(f"{TOKENINFO_URL}?{urlencode({'id_token': id_token})}")
    issuer = str(payload.get("iss") or "")
    audience = str(payload.get("aud") or "")
    if issuer not in GOOGLE_ISSUERS:
        raise ValueError("Google token issuer is not valid")
    if audience not in allowed_audiences():
        raise ValueError("Google token is not for this app")
    profile = _profile_from_payload(payload)
    if not profile["sub"] or not profile["email"]:
        raise ValueError("Google did not return an email for this account")
    return profile
