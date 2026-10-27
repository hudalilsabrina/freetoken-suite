"""Tempik disposable-mail adapter: mint an address, wait for a code OR a link.

Inception verifies new accounts with an activation LINK
(`/auth/verify?token=...`), not a numeric OTP, and the link usually arrives
wrapped in a tracking redirect — so both the raw link and the percent-encoded
destination inside a tracker are extracted.
"""
import json, random, re, string, time, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")

CODE_RE = [re.compile(r"\b(\d{6})\b"), re.compile(r"code[:\s]*([A-Za-z0-9]{4,10})", re.I)]
LINK_RE = re.compile(r"https?://[^\s\"'<>]+/auth/verify\?token=[A-Za-z0-9._\-]+")
TRACKED_RE = re.compile(r"https?%3A%2F%2F[^\s\"'<>]*auth%2Fverify%3Ftoken%3D([A-Za-z0-9._\-]+)")


class TempikMail:
    def __init__(self, base, domain, timeout=15):
        self.base, self.domain, self.timeout = base.rstrip("/"), domain, timeout
        self.session_id = None
        try:
            self.session_id = self._req("/api/session").get("sessionId")
        except Exception:
            pass

    def _req(self, path, method="GET", data=None):
        headers = {"User-Agent": UA}
        if self.session_id:
            headers["x-session-id"] = self.session_id
        payload = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(data).encode()
        req = urllib.request.Request(f"{self.base}{path}", data=payload, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode())

    def new_address(self, local_part=None):
        local_part = local_part or ("inc" + "".join(random.choices(string.ascii_lowercase + string.digits, k=9)))
        res = self._req("/api/inboxes", method="POST", data={"domain": self.domain, "localPart": local_part})
        return res["address"]

    def messages(self, address):
        try:
            m = self._req(f"/api/inboxes/{address}/messages")
            return m if isinstance(m, list) else []
        except Exception:
            return []

    @staticmethod
    def _blob(m):
        return " ".join(str(m.get(k) or "") for k in ("subject", "preview", "body", "text", "html"))

    def find_link(self, address, base_url="https://platform.inceptionlabs.ai"):
        for m in self.messages(address):
            blob = self._blob(m)
            hit = LINK_RE.search(blob)
            if hit:
                return hit.group(0).rstrip(").,")
            hit = TRACKED_RE.search(blob)
            if hit:
                return f"{base_url}/auth/verify?token={hit.group(1)}"
        return None

    def wait_link(self, address, base_url="https://platform.inceptionlabs.ai", timeout=180, interval=4):
        start = time.time()
        while time.time() - start < timeout:
            link = self.find_link(address, base_url)
            if link:
                return link
            time.sleep(interval)
        return None

    def wait_code(self, address, timeout=180, interval=4):
        start = time.time()
        while time.time() - start < timeout:
            for m in self.messages(address):
                if m.get("code"):
                    return str(m["code"])
                blob = self._blob(m)
                for pat in CODE_RE:
                    hit = pat.search(blob)
                    if hit:
                        return hit.group(1)
            time.sleep(interval)
        return None
