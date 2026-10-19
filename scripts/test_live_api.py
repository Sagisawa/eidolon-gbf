import json
import sys
import httpx

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

client = httpx.Client(
    base_url="http://127.0.0.1:8000",
    headers={"Origin": "http://127.0.0.1:8000"},
    timeout=60.0,
)

# 1. Characters list
res = client.get("/api/characters")
print("1. GET /api/characters:", res.status_code)
chars = res.json()
print("   Loaded characters:", [f"{c['id']} ({c['name']})" for c in chars])

# 2. Dev login as 古兰
login_res = client.post("/api/auth/dev-login", json={"name": "古兰"})
print("2. POST /api/auth/dev-login:", login_res.status_code)
assert login_res.status_code == 204, f"Login failed: {login_res.text}"

# 3. Account consent
consent_res = client.post("/api/account/consent")
print("3. POST /api/account/consent:", consent_res.status_code)

# 4. Create conversation with Narmaya
conv_res = client.post("/api/conversations", json={"character_id": "narmaya"})
print("4. POST /api/conversations (narmaya):", conv_res.status_code)
conv_id = conv_res.json()["id"]

# 5. SSE streaming turn
print("5. POST /api/conversations/{id}/turns (streaming SSE with local LLM):")
reply_parts = []
with client.stream(
    "POST",
    f"/api/conversations/{conv_id}/turns",
    json={"text": "姐姐，今天工会战好累呀，可以抱抱吗？"},
) as response:
    for line in response.iter_lines():
        if line.startswith("data: "):
            payload = json.loads(line[6:])
            if "text" in payload:
                text = payload["text"]
                reply_parts.append(text)
                print(text, end="", flush=True)

print("\n--- End of turn with Narmaya ---")
full_reply = "".join(reply_parts)
assert len(full_reply) > 0, "Empty reply received"
print("SUCCESS: Live SSE conversation verified with Narmaya!")

# 6. Test Vikala
conv_res2 = client.post("/api/conversations", json={"character_id": "vikala"})
print("6. POST /api/conversations (vikala):", conv_res2.status_code)
conv_id2 = conv_res2.json()["id"]

print("7. POST /api/conversations/{id}/turns (streaming SSE with Vikala):")
reply_parts2 = []
with client.stream(
    "POST",
    f"/api/conversations/{conv_id2}/turns",
    json={"text": "维卡拉，今天精神怎么样？"},
) as response:
    for line in response.iter_lines():
        if line.startswith("data: "):
            payload = json.loads(line[6:])
            if "text" in payload:
                text = payload["text"]
                reply_parts2.append(text)
                print(text, end="", flush=True)

print("\n--- End of turn with Vikala ---")
full_reply2 = "".join(reply_parts2)
assert len(full_reply2) > 0, "Empty reply received"
print("SUCCESS: Live SSE conversation verified with Vikala!")
