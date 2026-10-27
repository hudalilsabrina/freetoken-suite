"""Provision FreeToken accounts without signup.

The SPA builds the whole user object client-side — balance ($60), API key
(`sk-tf-` + 32 random chars), referral code — stores it in localStorage and then
POSTs it to `/api/user/sync`. That endpoint accepts the object verbatim and the
key is immediately live on the gateway, so no email OTP (their mailer is down)
and no GitHub OAuth is required.
"""
import json
import os
import random
import string
import time
import urllib.error
import urllib.request

BASE = "https://freetoken.website"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"


def gen_key():
    return "sk-tf-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=32))


def gen_email(domain=None):
    domain = domain or os.getenv("FREETOKEN_MAIL_DOMAIN", "example.com")
    return "ft" + "".join(random.choices(string.ascii_lowercase + string.digits, k=10)) + "@" + domain


def _post(path, payload, timeout=45):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Origin": BASE, "Referer": BASE + "/",
                 "User-Agent": UA},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except Exception as e:  # noqa: BLE001
        return -1, str(e)[:200]


def build_user(email, key, balance=60):
    local = email.split("@")[0]
    today = time.strftime("%Y-%m-%d")
    return {
        "email": email, "username": local, "balance": balance, "dailyClaimedDate": "",
        "apiKeys": [{"id": "key-1", "name": "Root Gateway Key", "key": key,
                     "created": today, "status": "active", "usage": 0}],
        "usageLogs": [], "referrals": [], "referralCode": local,
    }


def provision(email_domain=None, balance=60):
    """Create one account. Returns {ok, email, key, status}."""
    email = gen_email(email_domain)
    key = gen_key()
    st, body = _post("/api/user/sync", build_user(email, key, balance))
    ok = st == 200 and isinstance(body, dict) and body.get("success")
    return {"ok": bool(ok), "email": email, "key": key, "status": st,
            "balance": body.get("user", {}).get("balance") if isinstance(body, dict) else None}


def chat(key, model="auto", prompt="Say OK", max_tokens=16, timeout=60):
    body = json.dumps({"model": model, "max_tokens": max_tokens,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(BASE + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + key, "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read())
            return r.status, (d.get("choices") or [{}])[0].get("message", {}).get("content", "")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]
    except Exception as e:  # noqa: BLE001
        return -1, str(e)[:150]
