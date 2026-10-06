"""
ApexGPT — memory.py
Memoria persistente con Cloudflare D1.
"""

import time
import uuid
import json
import re
import requests

from config import (
    D1_API_URL,
    D1_API_SECRET,
    MODEL_NAME,
    ollama_client,
)


# ============================================================
# HELPERS D1
# ============================================================

def _d1_headers():
    return {
        "Authorization": f"Bearer {D1_API_SECRET}",
        "Content-Type": "application/json",
    }


def _d1_query_all(query: str, params=None):
    if not D1_API_URL or not D1_API_SECRET:
        print("[D1] No configurado, devolviendo []")
        return []
    try:
        response = requests.post(
            f"{D1_API_URL}/query/all",
            headers=_d1_headers(),
            json={"queryText": query, "params": params or []},
            timeout=10,
        )
        if not response.ok:
            print(f"[D1] Error {response.status_code}: {response.text[:200]}")
            return []
        data = response.json()
        if isinstance(data, dict):
            return data.get("results", []) or []
        return []
    except Exception as e:
        print(f"[D1] Error de conexión (all): {e}")
        return []


def _d1_query_run(query: str, params=None) -> bool:
    if not D1_API_URL or not D1_API_SECRET:
        print("[D1] No configurado, no se ejecuta la query")
        return False
    try:
        response = requests.post(
            f"{D1_API_URL}/query/run",
            headers=_d1_headers(),
            json={"queryText": query, "params": params or []},
            timeout=10,
        )
        if not response.ok:
            print(f"[D1] Error {response.status_code}: {response.text[:200]}")
            return False
        return True
    except Exception as e:
        print(f"[D1] Error de conexión (run): {e}")
        return False


def init_memory_db():
    if not D1_API_URL or not D1_API_SECRET:
        print("[D1] init_memory_db: sin configuración, se omite.")
        return

    ok1 = _d1_query_run("""
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            uid TEXT NOT NULL,
            text TEXT NOT NULL,
            category TEXT DEFAULT 'otro',
            created_at INTEGER NOT NULL,
            source TEXT DEFAULT 'auto'
        )
    """)
    ok2 = _d1_query_run("""
        CREATE INDEX IF NOT EXISTS idx_uid ON memories(uid)
    """)
    print(f"[D1] Tabla memories verificada (create={ok1}, index={ok2})")


# ============================================================
# CRUD DE MEMORIAS
# ============================================================

def get_user_memories(uid, limit=50):
    if not uid:
        return []
    try:
        rows = _d1_query_all(
            "SELECT id, text, category, created_at, source FROM memories "
            "WHERE uid = ? ORDER BY created_at DESC LIMIT ?",
            [uid, limit],
        )
        return [
            {
                "id": r.get("id"),
                "text": r.get("text"),
                "category": r.get("category"),
                "created_at": r.get("created_at"),
                "source": r.get("source"),
            }
            for r in rows
        ]
    except Exception as e:
        print(f"[Memory] Error leyendo memorias: {e}")
        return []


def save_user_memory(uid, memory_obj):
    if not uid or not memory_obj:
        return
    try:
        text = (memory_obj.get("text") or "").strip()
        if not text:
            return

        existing = _d1_query_all(
            "SELECT id FROM memories WHERE uid = ? AND LOWER(text) = LOWER(?)",
            [uid, text],
        )
        if existing:
            return

        memory_id = memory_obj.get("id") or str(uuid.uuid4())
        category = memory_obj.get("category", "otro")
        created_at = memory_obj.get("created_at") or int(time.time())
        source = memory_obj.get("source", "auto")

        _d1_query_run(
            "INSERT INTO memories (id, uid, text, category, created_at, source) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [memory_id, uid, text[:500], category, created_at, source],
        )
        print(f"[Memory] Guardado: {text[:80]}...")
    except Exception as e:
        print(f"[Memory] Error guardando memoria: {e}")


def delete_user_memory(uid, memory_id):
    return _d1_query_run(
        "DELETE FROM memories WHERE uid = ? AND id = ?",
        [uid, memory_id],
    )


def delete_all_user_memories(uid):
    return _d1_query_run(
        "DELETE FROM memories WHERE uid = ?",
        [uid],
    )


# ============================================================
# AUTO-APRENDIZAJE
# ============================================================

def extract_memories_from_conversation(user_message, assistant_response):
    if not user_message or not user_message.strip():
        return []

    # Saltar mensajes triviales (evita gastar cuota)
    if len(user_message.strip()) < 15:
        return []

    try:
        prompt = f"""Analiza este intercambio y extrae SOLO hechos duraderos sobre el usuario.
NO extraigas información temporal ni cosas triviales.

REGLAS:
- Solo hechos que sigan siendo ciertos en el futuro (nombre, profesión, gustos, ubicación, familia, metas).
- NO extraigas saludos, preguntas temporales, ni cosas que cambian cada día.
- Cada hecho debe ser una frase corta y clara, en tercera persona.
- Máximo 3 hechos por conversación.
- Clasifica cada hecho con una categoría: identidad, preferencias, trabajo, hobby, otro.

FORMATO de respuesta (JSON estricto, sin texto extra):
[{{"text": "El usuario se llama Josuexs", "category": "identidad"}}]

Si no hay hechos duraderos, responde con: []

CONVERSACIÓN:
Usuario: {user_message[:500]}
Asistente: {assistant_response[:500]}

JSON:"""

        response = ollama_client.chat(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            options={"num_ctx": 2000}
        )

        content = (response.message.content or "").strip()
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)

        try:
            hechos = json.loads(content)
        except json.JSONDecodeError:
            print(f"[Memory] JSON inválido: {content[:200]}")
            return []

        if not isinstance(hechos, list):
            return []

        resultado = []
        for h in hechos[:3]:
            if isinstance(h, dict) and h.get("text"):
                resultado.append({
                    "id": str(uuid.uuid4()),
                    "text": str(h["text"]).strip()[:300],
                    "category": h.get("category", "otro"),
                    "created_at": int(time.time()),
                    "source": "auto"
                })
        return resultado

    except Exception as e:
        print(f"[Memory] Error extrayendo: {e}")
        return []