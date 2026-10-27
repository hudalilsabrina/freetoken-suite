"""Set an arbitrary balance on accounts we own.

`balance` is a client-supplied field: `/api/user/sync` stores whatever number it
is handed and the gateway spends against it, with no cap or validation. That is
a trust hole on their side, so keep the number plausible — a fresh account with
$1,000,000 is the one pattern that gets a whole pool audited and wiped.
"""
import json
import urllib.parse
import urllib.request

from .daily import _get_user, _sync


def set_balance(email, amount):
    try:
        user = _get_user(email)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "status": "fetch_fail", "err": str(e)[:80]}
    before = float(user.get("balance") or 0)
    user["balance"] = float(amount)
    st, body = _sync(user)
    ok = st == 200 and isinstance(body, dict) and body.get("success")
    after = float((body.get("user") or {}).get("balance", before)) if ok else before
    return {"ok": bool(ok), "status": st, "before": before, "after": after}
