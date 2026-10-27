#!/usr/bin/env python3
"""FreeToken suite — model catalog, key capture, 9router injection.

  ./run.sh models                 list gateway models (public endpoint)
  ./run.sh chat -m auto -p "hi"   chat completion with a stored key
  ./run.sh otp --email a@b.c      send + verify an email OTP (their mailer is flaky)
  ./run.sh github                 print the GitHub OAuth URL to authorize in a browser
  ./run.sh add --key sk-tf-...    inject a key into 9router
  ./run.sh verify                 chat-test every stored key
  ./run.sh status                 local keys / 9router connections
  ./run.sh health                 is the gateway up? (checks for 522)
"""
import argparse, json, os, sys, time, tomllib, urllib.parse
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from src.client import FreeTokenClient, FreeTokenError
from src.daily import claim as daily_claim
from src.provision import chat as pchat
from src.topup import set_balance
from src.provision import provision
from src.router import add_key, upsert_provider

DATA = BASE / "data"
KEYS = DATA / "keys.txt"
ACCOUNTS = DATA / "accounts.jsonl"


def cfg():
    path = BASE / "config.toml"
    if not path.exists():
        path = BASE / "config.example.toml"
    with open(path, "rb") as f:
        return tomllib.load(f)


def log(m):
    line = f"[{time.strftime('%H:%M:%S')}] {m}"
    print(line, flush=True)
    (BASE / "logs").mkdir(exist_ok=True)
    with open(BASE / "logs" / "run.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def keys():
    if not KEYS.exists():
        return []
    return [k.strip() for k in KEYS.read_text().splitlines() if k.strip()]


def first_key():
    k = keys()
    return k[-1] if k else os.getenv("FREETOKEN_API_KEY", "")


def cmd_models(c, a):
    cli = FreeTokenClient(base=c["platform"]["base"])
    for m in cli.models():
        print(f"  {m.get('id'):26s} ctx={m.get('context_length')} "
              f"in={m.get('input_cost_per_m')} out={m.get('output_cost_per_m')}")
    return 0


def cmd_chat(c, a):
    cli = FreeTokenClient(a.key or first_key(), c["platform"]["base"])
    try:
        d = cli.chat(model=a.model, prompt=a.prompt, max_tokens=a.max_tokens)
        print(d["choices"][0]["message"]["content"])
        return 0
    except FreeTokenError as e:
        log(f"ERR {e.status}: {json.dumps(e.body)[:200] if isinstance(e.body, dict) else str(e.body)[:200]}")
        return 1


def cmd_health(c, a):
    cli = FreeTokenClient(base=c["platform"]["base"])
    t0 = time.time()
    try:
        ms = cli.models()
        log(f"models OK: {len(ms)} model, {(time.time()-t0)*1000:.0f} ms")
        return 0
    except FreeTokenError as e:
        log(f"models FAIL: {e.status} {str(e.body)[:120]}")
        return 1


def cmd_otp(c, a):
    from src.mail import TempikMail
    cli = FreeTokenClient(base=c["platform"]["base"])
    email = a.email
    if not email:
        mail = TempikMail(c["mail"]["base"], c["mail"]["domain"])
        email = mail.new_address()
    log(f"email={email}")
    st, d = cli.send_otp(email)
    log(f"send-otp: {st} {json.dumps(d)[:160] if isinstance(d, dict) else d}")
    if st != 200:
        log("mailer mereka sedang gagal (server-side 500) — pakai jalur GitHub OAuth")
        return 1
    if not a.email:
        code = mail.wait_code(email, timeout=120)
        log(f"otp={code}")
        if not code:
            return 1
        st2, d2 = cli.verify_otp(email, code)
        log(f"verify-otp: {st2} {json.dumps(d2)[:200] if isinstance(d2, dict) else d2}")
        return 0 if st2 == 200 else 1
    return 0


def cmd_github(c, a):
    url = (c["platform"]["base"] + c["platform"]["github_login"])
    log("Buka URL ini di browser yang sudah login GitHub:")
    print(url)
    log("Setelah authorize, callback akan mendarat di /api/auth/github/callback")
    log("Ambil API key di dashboard lalu: ./run.sh add --key sk-tf-...")
    return 0


def cmd_add(c, a):
    pid = upsert_provider(c["router"]["db"], c["router"]["provider"], c["router"]["prefix"],
                          c["platform"]["api"], c["router"]["node_name"])
    cid = add_key(c["router"]["db"], pid, a.key, a.label, c["platform"]["api"],
                  c["router"]["prefix"])
    if cid:
        DATA.mkdir(exist_ok=True)
        with open(KEYS, "a", encoding="utf-8") as f:
            f.write(a.key + "\n")
        log(f"injected {cid}")
        return 0
    log("already present")
    return 1


def cmd_verify(c, a):
    ks = keys()[-a.limit:]
    if not ks:
        log("no keys stored")
        return 1
    for k in ks:
        cli = FreeTokenClient(k, c["platform"]["base"])
        try:
            d = cli.chat(model=a.model, prompt="Say OK", max_tokens=16)
            log(f"{k[:12]}… {a.model} -> {(d['choices'][0]['message']['content'] or '')[:24]!r}")
        except FreeTokenError as e:
            log(f"{k[:12]}… {a.model} -> ERR {e.status} {str(e.body)[:80]}")
    return 0


def cmd_provision(c, a):
    """Create N accounts via /api/user/sync (no email, no OTP, no OAuth)."""
    DATA.mkdir(exist_ok=True)
    made = 0
    for i in range(1, a.count + 1):
        r = provision(c["mail"]["domain"], a.balance)
        if not r["ok"]:
            log(f"[{i}/{a.count}] FAIL status={r['status']}")
            time.sleep(a.gap)
            continue
        st, txt = pchat(r["key"], a.model)
        log(f"[{i}/{a.count}] {r['email']} balance={r['balance']} probe={st} {str(txt)[:24]!r}")
        # Persist on sync success even when the probe 502s: the account exists and
        # the key was generated client-side, so an unsaved key is unrecoverable.
        made += 1
        with open(KEYS, "a", encoding="utf-8") as f:
            f.write(r["key"] + "\n")
        with open(ACCOUNTS, "a", encoding="utf-8") as f:
            f.write(json.dumps({"email": r["email"], "key": r["key"],
                                "balance": r["balance"], "model": a.model,
                                "probe": st}) + "\n")
        time.sleep(a.gap)
    log(f"provisioned {made}/{a.count}")
    return 0 if made else 1


def cmd_sync(c, a):
    """Inject every stored key into 9router."""
    ks = keys()
    if not ks:
        log("belum ada key — jalankan provision dulu")
        return 1
    pid = upsert_provider(c["router"]["db"], c["router"]["provider"], c["router"]["prefix"],
                          c["platform"]["api"], c["router"]["node_name"])
    added = 0
    for k in ks:
        cid = add_key(c["router"]["db"], pid, k, f"ft-{k[-6:]}", c["platform"]["api"],
                      c["router"]["prefix"])
        if cid:
            added += 1
    log(f"inject {added} key baru (total lokal {len(ks)})")
    return 0


def cmd_claim(c, a):
    """Claim the $5 daily reward for every stored account."""
    rows = []
    if ACCOUNTS.exists():
        rows = [json.loads(l) for l in ACCOUNTS.read_text().splitlines() if l.strip()]
    if not rows:
        log("belum ada akun")
        return 1
    gained = 0.0
    claimed = already = failed = 0
    for i, r in enumerate(rows, 1):
        res = daily_claim(r["email"])
        if res.get("ok"):
            claimed += 1
            gained += res["after"] - res["before"]
            log(f"[{i}/{len(rows)}] +${res['after']-res['before']:.2f} -> ${res['after']:.2f} {r['email']}")
        elif res.get("status") == "already":
            already += 1
        else:
            failed += 1
            log(f"[{i}/{len(rows)}] FAIL {res.get('status')} {r['email']}")
        time.sleep(a.gap)
    log(f"claim selesai: {claimed} klaim (+${gained:.2f}) | {already} sudah | {failed} gagal")
    return 0


def cmd_topup(c, a):
    """Overwrite the stored balance on existing accounts."""
    rows = []
    if ACCOUNTS.exists():
        rows = [json.loads(l) for l in ACCOUNTS.read_text().splitlines() if l.strip()]
    if not rows:
        log("belum ada akun")
        return 1
    if a.limit:
        rows = rows[:a.limit]
    ok = 0
    gained = 0.0
    for i, r in enumerate(rows, 1):
        res = set_balance(r["email"], a.balance)
        if res.get("ok"):
            ok += 1
            gained += res["after"] - res["before"]
            if i % 10 == 0 or i == len(rows):
                log(f"[{i}/{len(rows)}] {r['email']} ${res['before']:.2f} -> ${res['after']:.2f}")
        else:
            log(f"[{i}/{len(rows)}] FAIL {res.get('status')} {r['email']}")
        time.sleep(a.gap)
    log(f"topup selesai: {ok}/{len(rows)} akun | delta ${gained:,.2f}")
    return 0


def cmd_status(c, a):
    import sqlite3
    ks = len(keys())
    try:
        conn = sqlite3.connect(c["router"]["db"])
        cn = conn.execute("SELECT COUNT(*) FROM providerConnections WHERE provider=?",
                          (c["router"]["provider"],)).fetchone()[0]
        conn.close()
    except Exception:
        cn = "?"
    log(f"api key lokal={ks} | koneksi 9router={cn}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("models").set_defaults(fn=cmd_models)
    sub.add_parser("health").set_defaults(fn=cmd_health)
    sub.add_parser("github").set_defaults(fn=cmd_github)
    sub.add_parser("status").set_defaults(fn=cmd_status)

    p = sub.add_parser("chat")
    p.add_argument("-m", "--model", default="auto")
    p.add_argument("-p", "--prompt", required=True)
    p.add_argument("--max-tokens", type=int, default=64)
    p.add_argument("--key", default="")
    p.set_defaults(fn=cmd_chat)

    p = sub.add_parser("otp")
    p.add_argument("--email", default="")
    p.set_defaults(fn=cmd_otp)

    p = sub.add_parser("add")
    p.add_argument("--key", required=True)
    p.add_argument("--label", default="manual")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("provision")
    p.add_argument("-n", "--count", type=int, default=5)
    p.add_argument("--balance", type=int, default=60)
    p.add_argument("--model", default="auto")
    p.add_argument("--gap", type=int, default=3)
    p.set_defaults(fn=cmd_provision)

    sub.add_parser("sync").set_defaults(fn=cmd_sync)

    p = sub.add_parser("topup")
    p.add_argument("--balance", type=float, required=True)
    p.add_argument("-n", "--limit", type=int, default=0)
    p.add_argument("--gap", type=float, default=0.3)
    p.set_defaults(fn=cmd_topup)

    p = sub.add_parser("claim")
    p.add_argument("--gap", type=float, default=0.4)
    p.set_defaults(fn=cmd_claim)

    p = sub.add_parser("verify")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--model", default="auto")
    p.set_defaults(fn=cmd_verify)

    args = ap.parse_args()
    return args.fn(cfg(), args)


if __name__ == "__main__":
    sys.exit(main())
