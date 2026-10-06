"""
ApexGPT — tools.py
Herramientas del agente: YouTube, búsqueda de imágenes.
(web_search y web_fetch se importan directo de ollama en agent.py)
"""

import re
import time
import requests
from urllib.parse import quote

from config import (
    SUPADATA_API_KEY,
    SUPADATA_TRANSCRIPT_URL,
    SUPADATA_POLL_MAX_ATTEMPTS,
    SUPADATA_POLL_DELAY_SECONDS,
)


# ============================================================
# YOUTUBE — SUPADATA
# ============================================================

def youtube_fetch(url: str) -> str:
    match = re.search(
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
        url
    )

    if not match:
        return "No pude identificar un ID válido de YouTube en esa URL."

    if not SUPADATA_API_KEY:
        return ("No se puede obtener la transcripción porque falta "
                "configurar SUPADATA_API_KEY en el servidor.")

    headers = {"x-api-key": SUPADATA_API_KEY}
    params = {"url": url, "text": "true"}

    try:
        response = requests.get(
            SUPADATA_TRANSCRIPT_URL,
            headers=headers,
            params=params,
            timeout=30
        )

        if response.status_code == 202:
            job_id = response.json().get("jobId")
            if not job_id:
                return "Supadata devolvió un job asíncrono sin jobId."

            job_url = f"{SUPADATA_TRANSCRIPT_URL}/{job_id}"

            for _ in range(SUPADATA_POLL_MAX_ATTEMPTS):
                time.sleep(SUPADATA_POLL_DELAY_SECONDS)
                poll_response = requests.get(job_url, headers=headers, timeout=30)
                poll_data = poll_response.json()
                status = poll_data.get("status")

                if status == "completed":
                    text = poll_data.get("content", "")
                    return str(text)[:12000] if text else "La transcripción llegó vacía."

                if status == "failed":
                    return "Supadata no pudo generar la transcripción."

            return "La transcripción está tardando demasiado. Intenta de nuevo."

        if response.status_code == 404:
            return "El video no existe, es privado o no está disponible."

        if response.status_code == 403:
            return "El video requiere autenticación o está restringido."

        if not response.ok:
            return f"Supadata devolvió HTTP {response.status_code}."

        data = response.json()
        text = data.get("content", "")

        if not text or not str(text).strip():
            return "El video no tiene ninguna transcripción disponible."

        return str(text)[:12000]

    except requests.exceptions.RequestException as error:
        print("Error de red llamando a Supadata:", repr(error))
        return f"No pude conectarme a Supadata. Error: {error}"

    except Exception as error:
        print("Error obteniendo transcripción:", repr(error))
        return f"Error técnico obteniendo transcripción: {error}"


# ============================================================
# BÚSQUEDA DE IMÁGENES
# ============================================================

def image_search(query: str, max_results: int = 6):
    try:
        max_results = int(max_results) if max_results else 6
    except (TypeError, ValueError):
        max_results = 6

    try:
        search_url = f"https://www.bing.com/images/search?q={quote(query)}"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0 Safari/537.36"
            )
        }

        response = requests.get(search_url, headers=headers, timeout=15)
        response.raise_for_status()

        html = response.text
        results = []

        matches = re.findall(r'murl&quot;:&quot;(.*?)&quot;', html)

        for image_url in matches:
            image_url = image_url.replace("\\/", "/").replace("&amp;", "&")

            if not image_url.startswith("http"):
                continue

            if any(item["url"] == image_url for item in results):
                continue

            results.append({"url": image_url, "title": query})

            if len(results) >= max_results:
                break

        print(f"Búsqueda de imágenes: '{query}' -> {len(results)} resultados")
        return results

    except Exception as error:
        print("Error buscando imágenes:", repr(error))
        return []