"""FreeToken gateway client (OpenAI-compatible) + account API helpers.

The gateway itself is a New API instance behind Cloudflare: unauthenticated or
quota-exhausted calls surface as `new_api_error` JSON, and the origin sometimes
answers 522 while it restarts. Every call here reports the raw status so the
caller can distinguish "our key is bad" from "their box is down".
"""
import json
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")


class FreeTokenError(Exception):
    def __init__(self, msg, status=None, body=None):
        super().__init__(msg)
        self.status = status
        self.body = body


class FreeTokenClient:
    def __init__(self, api_key="", base="https://freetoken.website", timeout=60):
        self.api_key = api_key
        self.base = base.rstrip("/")
        self.timeout = timeout

    def _req(self, path, payload=None, method=None, auth=True, raw=False):
        url = self.base + path
        headers = {"User-Agent": UA, "Accept": "application/json"}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode()
        if auth and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=data, headers=headers,
                                     method=method or ("POST" if data else "GET"))
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                body = r.read().decode()
                return r.status, (body if raw else json.loads(body))
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            try:
                return e.code, json.loads(body)
            except Exception:
                return e.code, body
        except Exception as e:
            raise FreeTokenError(f"connection failed: {e}")

    # --- OpenAI-compatible surface
    def models(self):
        st, d = self._req("/v1/models", auth=False)
        if st != 200 or not isinstance(d, dict):
            raise FreeTokenError(f"models failed ({st})", st, d)
        return d.get("data", [])

    def chat(self, model="auto", prompt="Say OK", max_tokens=32, messages=None):
        payload = {"model": model, "max_tokens": max_tokens,
                   "messages": messages or [{"role": "user", "content": prompt}]}
        st, d = self._req("/v1/chat/completions", payload)
        if st != 200:
            raise FreeTokenError(f"chat failed ({st})", st, d)
        return d

    # --- account surface (cookie-less: the SPA keys everything off email)
    def user_by_email(self, email):
        return self._req(f"/api/user/me?email={urllib.parse.quote(email)}", auth=False)

    def send_otp(self, email):
        return self._req("/api/send-otp", {"email": email}, auth=False)

    def verify_otp(self, email, code):
        return self._req("/api/verify-otp", {"email": email, "code": code}, auth=False)

    def sync_user(self, user_obj):
        return self._req("/api/user/sync", user_obj, auth=False)
