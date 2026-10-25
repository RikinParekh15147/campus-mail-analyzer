"""Real Google adapters. OAuth credentials remain in an OS credential vault."""

import json

SCOPES = {
    "gmail": ["https://www.googleapis.com/auth/gmail.readonly"],
    "calendar": [
        "https://www.googleapis.com/auth/calendar.app.created",
        "https://www.googleapis.com/auth/calendar.events.readonly",
        "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    ],
}


def default_vault():
    """Production vault factory; tests replace this with an isolated in-memory vault."""
    import keyring

    return keyring


class GoogleConnection:
    def __init__(self, owner, service, vault=None):
        if service not in SCOPES:
            raise ValueError("Unsupported Google service")
        if vault is None:
            vault = default_vault()
        self.owner, self.service, self.vault = owner, service, vault
        self.key = owner + ":" + service

    def connect(self, client_config):
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_config(client_config, SCOPES[self.service])
        credentials = flow.run_local_server(
            host="127.0.0.1", port=0, open_browser=True, timeout_seconds=180
        )
        self.vault.set_password("campusmail", self.key, credentials.to_json())
        return {"connected": True, "service": self.service}

    def disconnect(self):
        raw = self.vault.get_password("campusmail", self.key)
        if raw:
            import requests

            token = json.loads(raw).get("refresh_token") or json.loads(raw).get("token")
            response = requests.post(
                "https://oauth2.googleapis.com/revoke",
                data={"token": token},
                timeout=20,
            )
            if response.status_code not in (200, 400):
                response.raise_for_status()
            self.vault.delete_password("campusmail", self.key)

    def credentials(self):
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        raw = self.vault.get_password("campusmail", self.key)
        if not raw:
            raise ValueError("Connect " + self.service + " first")
        credentials = Credentials.from_authorized_user_info(
            json.loads(raw), SCOPES[self.service]
        )
        if not credentials.valid:
            if not credentials.refresh_token:
                raise ValueError("Google access expired; reconnect")
            credentials.refresh(Request())
            self.vault.set_password("campusmail", self.key, credentials.to_json())
        return credentials

    def status(self):
        try:
            return {
                "connected": bool(self.vault.get_password("campusmail", self.key)),
                "service": self.service,
            }
        except Exception:
            return {
                "connected": False,
                "service": self.service,
                "error": "OS credential vault unavailable",
            }


class GoogleHTTP:
    def __init__(self, connection):
        from google.auth.transport.requests import AuthorizedSession

        self.connection = connection
        self.session = AuthorizedSession(connection.credentials())
        self.base = (
            "https://gmail.googleapis.com/gmail/v1/users/me/"
            if connection.service == "gmail"
            else "https://www.googleapis.com/calendar/v3/"
        )

    def request(self, method, path, **kwargs):
        response = self.session.request(method, self.base + path, timeout=45, **kwargs)
        if response.status_code in (404, 410):
            raise LookupError("Provider cursor/resource unavailable")
        response.raise_for_status()
        if self.session.credentials.refresh_token:
            self.connection.vault.set_password(
                "campusmail", self.connection.key, self.session.credentials.to_json()
            )
        return response.json() if response.content else {}

    def get(self, path, params=None):
        return self.request("GET", path, params=params)

    def post(self, path, json):
        return self.request("POST", path, json=json)

    def patch(self, path, json):
        return self.request("PATCH", path, json=json)

    def delete(self, path):
        return self.request("DELETE", path)
