"""Daily reward claim — mirrors the SPA's client-side claim.

The dashboard's "Claim Daily Reward" button does not call a dedicated endpoint:
it takes the user object, adds $5.00, stamps `dailyClaimedDate` with today, pushes
a usage log with cost -5 and POSTs the whole object back to `/api/user/sync`.
Same trick as provisioning, so it works for every account we own.
"""
import json
import time
import urllib.error
import urllib.request

BASE = "https://freetoken.website"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36")
REWARD = 5.0


def _get_user(email, timeout=25):
    req = urllib.request.Request(f"{BASE}/api/user/me?email={urllib.parse.quote(email)}",
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["user"]


def _sync(user, timeout=40):
    req = urllib.request.Request(BASE + "/api/user/sync", data=json.dumps(user).encode(),
                                 headers={"Content-Type": "application/json", "Origin": BASE,
                                          "Referer": BASE + "/", "User-Agent": UA},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]
    except Exception as e:  # noqa: BLE001
        return -1, str(e)[:150]


def claim(email, today=None):
    """Claim today's reward for one account. Returns {ok, status, before, after}."""
    today = today or time.strftime("%Y-%m-%d")
    try:
        user = _get_user(email)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "status": "fetch_fail", "err": str(e)[:80]}
    before = float(user.get("balance") or 0)
    if user.get("dailyClaimedDate") == today:
        return {"ok": False, "status": "already", "before": before, "after": before}
    user["balance"] = before + REWARD
    user["dailyClaimedDate"] = today
    logs = user.get("usageLogs") or []
    logs.append({"id": f"claim-{int(time.time() * 1000)}",
                 "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                 "model": "Daily Reward Claim", "tokens": 0, "cost": -REWARD,
                 "status": "Success"})
    user["usageLogs"] = logs
    st, body = _sync(user)
    ok = st == 200 and isinstance(body, dict) and body.get("success")
    return {"ok": bool(ok), "status": st, "before": before,
            "after": float((body.get("user") or {}).get("balance", before)) if ok else before}


import urllib.parse  # noqa: E402  (kept last so the module reads top-down)
