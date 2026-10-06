"""
ApexGPT — config.py
Configuración central: variables de entorno y clientes externos.
"""

import os
from ollama import Client
from huggingface_hub import InferenceClient


# ============================================================
# OLLAMA CLOUD
# ============================================================

MODEL_NAME = os.environ.get("OLLAMA_MODEL", "gemma4:31b-cloud")
OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY", "").strip()

if not OLLAMA_API_KEY:
    print("ADVERTENCIA: OLLAMA_API_KEY no está configurada.")
else:
    print(f"OLLAMA_API_KEY configurada. Modelo: {MODEL_NAME}")

ollama_client = Client(
    host="https://ollama.com",
    headers={"Authorization": f"Bearer {OLLAMA_API_KEY}"}
)


# ============================================================
# CLOUDFLARE D1
# ============================================================

D1_API_URL = os.environ.get("D1_API_URL", "").strip().rstrip("/")
D1_API_SECRET = os.environ.get("D1_API_SECRET", "").strip()

if not D1_API_URL or not D1_API_SECRET:
    print("ADVERTENCIA: D1_API_URL o D1_API_SECRET no configuradas.")
else:
    print(f"D1 configurado: {D1_API_URL}")


# ============================================================
# HUGGING FACE
# ============================================================

HF_API_TOKEN = os.environ.get("HF_API_TOKEN", "").strip()

if not HF_API_TOKEN:
    print("ADVERTENCIA: HF_API_TOKEN no configurada. Generación de imágenes deshabilitada.")
else:
    print("HF_API_TOKEN configurada. Generación de imágenes habilitada.")

HF_MODEL_NAME = os.environ.get("HF_MODEL", "black-forest-labs/FLUX.1-schnell").strip()
print(f"[image-gen] Modelo configurado: {HF_MODEL_NAME}")

_hf_client = None


def get_hf_client():
    global _hf_client
    if _hf_client is None:
        _hf_client = InferenceClient(
            provider="auto",
            api_key=HF_API_TOKEN,
        )
    return _hf_client


# ============================================================
# SUPADATA (YouTube)
# ============================================================

SUPADATA_API_KEY = os.environ.get("SUPADATA_API_KEY", "").strip()

if not SUPADATA_API_KEY:
    print("ADVERTENCIA: SUPADATA_API_KEY no configurada. youtube_fetch no funcionará.")

SUPADATA_TRANSCRIPT_URL = "https://api.supadata.ai/v1/transcript"
SUPADATA_POLL_MAX_ATTEMPTS = 10
SUPADATA_POLL_DELAY_SECONDS = 2