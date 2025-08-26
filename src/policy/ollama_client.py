import requests, json, os, re

OLLAMA = os.getenv("OLLAMA_HOST", "http://localhost:11434")

def _parse_streaming_json(text: str):
    last = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            last = json.loads(line)
        except Exception:
            continue
    if last is None:
        raise ValueError("No JSON object found in streaming response")
    return last

def _extract_json_block(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(\w+)?\s*|\s*```$", "", s, flags=re.DOTALL)
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    return m.group(0) if m else s

def ask_policy(features_vec, meta):
    """
    Appelle Ollama et renvoie un dict Python (pas de promesse de forme finale).
    """
    sys_msg = {
        "role": "system",
        "content": (
            "Tu es un coach poker GTO-lite. Réponds STRICTEMENT en JSON avec les champs: "
            '{"action":"fold|call|raise|none","size_bb":float (optionnel),'
            '"percent":float (optionnel, fraction du pot, ex 0.5),'
            '"confidence":float [0..1] (optionnel),"reason":"..."}'
        )
    }
    user_msg = {
        "role": "user",
        "content": (
            f"STREET={meta['street']} POS={meta['position']} SPR={meta['spr']:.2f}\n"
            f"HAND={meta.get('hero_cards','?')} BOARD={meta.get('board_cards','?')}\n"
            f"FEATURES_HEAD={list(map(float, features_vec[:32]))}"
        )
    }
    body = {
        "model": os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
        "messages": [sys_msg, user_msg],
        "format": "json",
        "stream": False,  # IMPORTANT: pas de streaming ici
        "options": {"temperature": 0.2, "top_p": 0.9}
    }
    r = requests.post(f"{OLLAMA}/api/chat", json=body, timeout=60)
    r.raise_for_status()

    # essaye d'abord la réponse non streamée
    try:
        obj = r.json()
    except Exception:
        obj = _parse_streaming_json(r.text)

    content = obj.get("message", {}).get("content", "")
    try:
        return json.loads(_extract_json_block(content))
    except Exception:
        # si l’IA renvoie qqchose d’inattendu, renvoie 'none'
        return {"action": "none", "reason": "unparsable LLM output"}
