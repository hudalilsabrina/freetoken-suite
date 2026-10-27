"""Inject FreeToken keys into 9router as an OpenAI-compatible provider."""
import json
import sqlite3
import time
import uuid


def upsert_provider(db_path, provider, prefix, base_url, node_name="freetoken"):
    conn = sqlite3.connect(db_path)
    now = int(time.time() * 1000)
    data = {"prefix": prefix, "apiType": "chat", "baseUrl": base_url,
            "brand": "openai", "logo": "", "quotaEnabled": False}
    if not conn.execute("SELECT id FROM providerNodes WHERE id=?", (provider,)).fetchone():
        conn.execute("INSERT INTO providerNodes (id, type, name, data, createdAt, updatedAt)"
                     " VALUES (?,?,?,?,?,?)",
                     (provider, "openai-compatible", node_name, json.dumps(data), now, now))
    conn.commit()
    conn.close()
    return provider


def add_key(db_path, provider, api_key, label, base_url, prefix):
    conn = sqlite3.connect(db_path)
    if conn.execute("SELECT id FROM providerConnections WHERE provider=? AND data LIKE ?",
                    (provider, f"%{api_key[:20]}%")).fetchone():
        conn.close()
        return None
    payload = {
        "defaultModel": f"{prefix}/auto",
        "apiKey": api_key,
        "testStatus": "active",
        "providerSpecificData": {"prefix": prefix, "apiType": "chat", "baseUrl": base_url,
                                 "nodeName": "FreeToken Gateway"},
        "errorCode": None, "backoffLevel": 0, "lastError": None, "lastErrorAt": None,
        "rateLimitedUntil": None,
    }
    cid = str(uuid.uuid4())
    now = int(time.time() * 1000)
    conn.execute("INSERT INTO providerConnections (id, provider, authType, name, email, priority,"
                 " isActive, data, createdAt, updatedAt) VALUES (?,?,?,?,?,?,?,?,?,?)",
                 (cid, provider, "apikey", label, label, 10, 1, json.dumps(payload), now, now))
    conn.commit()
    conn.close()
    return cid
