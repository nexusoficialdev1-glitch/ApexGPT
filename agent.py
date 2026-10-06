"""
ApexGPT — agent.py
Construcción de mensajes + ejecución del agente con tool calling.
"""

from ollama import web_search, web_fetch

from config import MODEL_NAME, ollama_client
from prompts import APEXGPT_SYSTEM_PROMPT, IMAGE_ANALYSIS_ADDENDUM
from tools import youtube_fetch, image_search


# ============================================================
# HERRAMIENTAS DISPONIBLES
# ============================================================

available_tools = {
    "web_search": web_search,
    "web_fetch": web_fetch,
    "youtube_fetch": youtube_fetch,
    "image_search": image_search,
}


# ============================================================
# CONSTRUIR MENSAJES
# ============================================================

def build_messages(history, custom_instructions=None, user_image_base64=None, memories=None):
    messages = []

    system_prompt = APEXGPT_SYSTEM_PROMPT + IMAGE_ANALYSIS_ADDENDUM

    if memories and isinstance(memories, list):
        lines = []
        for m in memories:
            if isinstance(m, dict):
                cat = m.get("category", "otro")
                txt = m.get("text", "")
                if txt:
                    lines.append(f"- [{cat}] {txt}")
            elif isinstance(m, str):
                lines.append(f"- {m}")

        if lines:
            memories_text = "\n".join(lines)
            system_prompt += f"""

RECUERDOS SOBRE EL USUARIO (Información que conoces de conversaciones pasadas):
{memories_text}

Usa estos recuerdos para personalizar tus respuestas. NO los menciones
explícitamente ni digas "recuerdo que...". Simplemente intégralos con naturalidad.
"""

    if custom_instructions:
        if isinstance(custom_instructions, str):
            custom_instructions_text = custom_instructions

        elif isinstance(custom_instructions, dict):
            partes = []

            tone = custom_instructions.get("tone")
            if tone:
                tono_map = {
                    "formal": "Usa un tono formal y profesional.",
                    "casual": "Usa un tono casual, cercano y natural.",
                    "tecnico": "Usa un tono técnico, preciso, con terminología correcta.",
                    "divertido": "Usa un tono divertido, con humor ligero cuando encaje."
                }
                partes.append(tono_map.get(str(tone).lower(), f"Tono: {tone}"))

            length = custom_instructions.get("length")
            if length:
                longitud_map = {
                    "corta": "Da respuestas cortas y directas, sin rodeos.",
                    "media": "Da respuestas de longitud media, claras y completas.",
                    "larga": "Da respuestas extensas y detalladas cuando sea útil."
                }
                partes.append(longitud_map.get(str(length).lower(), f"Longitud: {length}"))

            language = custom_instructions.get("language")
            if language and language != "auto":
                idioma_map = {
                    "es": "Responde siempre en español.",
                    "en": "Always respond in English.",
                    "pt": "Responda sempre em português."
                }
                partes.append(idioma_map.get(str(language).lower(), f"Idioma: {language}"))

            concise = custom_instructions.get("concise")
            if concise is True:
                partes.append(
                    "Modo conciso activado: sé directo, evita introducciones, "
                    "no repitas la pregunta, ve al grano, sin relleno."
                )

            bot_name = custom_instructions.get("bot_name")
            if bot_name and isinstance(bot_name, str) and bot_name.strip():
                partes.append(
                    f"El usuario te llama '{bot_name.strip()}'. "
                    f"Adopta ese nombre como tu identidad cuando te presentes "
                    f"o cuando el usuario se refiera a ti."
                )

            deep_thinking = custom_instructions.get("deep_thinking")
            if deep_thinking is True:
                partes.append(
                    "MODO PENSAMIENTO PROFUNDO ACTIVADO:\n"
                    "- Piensa paso a paso antes de responder.\n"
                    "- Considera múltiples ángulos, matices y contraejemplos.\n"
                    "- Estructura la respuesta con razonamiento explícito cuando sea útil.\n"
                    "- No sacrifiques profundidad por brevedad.\n"
                    "- Si hay ambigüedad, explora las interpretaciones posibles.\n"
                    "- Usa ejemplos concretos y analogías cuando ayuden a entender.\n"
                    "- Puedes estructurar con subtítulos o listas cuando el tema sea complejo."
                )

            smart_search = custom_instructions.get("smart_search")
            if smart_search is True:
                partes.append(
                    "MODO BÚSQUEDA INTELIGENTE ACTIVADO (OBLIGATORIO):\n"
                    "- SIEMPRE debes usar web_search ANTES de responder. No respondas de memoria.\n"
                    "- Como mínimo, haz UNA búsqueda para verificar la información.\n"
                    "- Después de la búsqueda, responde basándote en los resultados.\n"
                    "- Menciona las fuentes que encontraste."
                )

            custom_instructions_text = "\n".join(f"- {p}" for p in partes if p)

        else:
            custom_instructions_text = str(custom_instructions)

        if custom_instructions_text.strip():
            system_prompt += f"""

PREFERENCIAS DEL USUARIO:

{custom_instructions_text}
"""

    messages.append({"role": "system", "content": system_prompt})

    for idx, item in enumerate(history):
        message = {
            "role": item.get("role", "user"),
            "content": item.get("content", "")
        }

        if message["content"] == "[Imagen]":
            message["content"] = "Analiza esta imagen."

        images = item.get("images")
        if images:
            image_urls = []
            for image in images:
                if isinstance(image, dict):
                    url = image.get("url")
                    if url and isinstance(url, str):
                        image_urls.append(url)
                elif isinstance(image, str):
                    image_urls.append(image)

            if image_urls:
                existing_content = str(message.get("content", ""))
                image_context = (
                    "\n\nImágenes encontradas anteriormente:\n"
                    + "\n".join(f"- {u}" for u in image_urls)
                )
                message["content"] = existing_content + image_context

        es_ultimo = (idx == len(history) - 1)
        if es_ultimo and user_image_base64 and message["role"] == "user":
            message["images"] = [user_image_base64]
            if not message["content"] or message["content"] == "Analiza esta imagen.":
                message["content"] = "Analiza esta imagen."

        messages.append(message)

    return messages


# ============================================================
# EXTRAER FUENTES DE WEB_SEARCH
# ============================================================

def extract_web_sources(raw_result) -> list:
    sources = []

    def add_source(url, title="", snippet=""):
        if url and isinstance(url, str) and url.startswith("http"):
            sources.append({
                "title": str(title or "Fuente web")[:200],
                "url": url,
                "snippet": str(snippet or "")[:300]
            })

    try:
        if hasattr(raw_result, "results"):
            results = raw_result.results
            if isinstance(results, list):
                for item in results:
                    add_source(
                        getattr(item, "url", None),
                        getattr(item, "title", None),
                        getattr(item, "content", None)
                    )

        elif isinstance(raw_result, list):
            for item in raw_result:
                if isinstance(item, dict):
                    add_source(
                        item.get("url") or item.get("link") or item.get("href"),
                        item.get("title") or item.get("name") or "",
                        item.get("snippet") or item.get("description") or item.get("content") or ""
                    )
                elif hasattr(item, "url"):
                    add_source(
                        getattr(item, "url", None),
                        getattr(item, "title", None),
                        getattr(item, "content", None)
                    )

        elif isinstance(raw_result, dict):
            results = raw_result.get("results") or raw_result.get("items") or []
            if isinstance(results, list):
                for item in results:
                    if isinstance(item, dict):
                        add_source(
                            item.get("url") or item.get("link") or item.get("href"),
                            item.get("title") or item.get("name") or "",
                            item.get("snippet") or item.get("description") or item.get("content") or ""
                        )

        elif isinstance(raw_result, str):
            import re
            urls = re.findall(r'https?://[^\s<>"\')\]]+', raw_result)
            for url in urls[:12]:
                add_source(url, "Fuente web", "")

    except Exception as e:
        import traceback
        print(f"[web_sources] Error extrayendo fuentes: {e}")
        traceback.print_exc()

    seen = set()
    unique = []
    for s in sources:
        if s["url"] not in seen:
            seen.add(s["url"])
            unique.append(s)

    print(f"[web_sources] Total extraídas: {len(unique)}")
    return unique[:15]


# ============================================================
# AGENTE
# ============================================================

MAX_TOOL_ITERATIONS = 6


def run_agent(messages):
    final_text = ""
    image_results = []
    web_sources = []

    tools = [web_search, web_fetch, youtube_fetch, image_search]

    for _ in range(MAX_TOOL_ITERATIONS):
        response = ollama_client.chat(
            model=MODEL_NAME,
            messages=messages,
            tools=tools,
            options={"num_ctx": 32000}
        )

        if response.message.content:
            final_text = response.message.content

        messages.append(response.message)

        if not response.message.tool_calls:
            break

        for tool_call in response.message.tool_calls:
            function_name = tool_call.function.name
            function_to_call = available_tools.get(function_name)

            if function_to_call:
                args = tool_call.function.arguments
                try:
                    result = function_to_call(**args)

                    if function_name == "image_search" and isinstance(result, list):
                        image_results.extend(result)

                    if function_name == "web_search":
                        print(f"[web_search] RAW type: {type(result).__name__}")
                        nuevas_fuentes = extract_web_sources(result)
                        web_sources.extend(nuevas_fuentes)
                        print(f"[web_search] '{args.get('query', '')[:40]}' -> {len(nuevas_fuentes)} fuentes")

                    result_text = str(result)[:12000]

                except Exception as error:
                    result_text = f"Error ejecutando la herramienta: {error}"
            else:
                result_text = f"Herramienta {function_name} no encontrada"

            messages.append({
                "role": "tool",
                "content": result_text,
                "tool_name": function_name
            })
    else:
        print(f"[agent] Se alcanzó MAX_TOOL_ITERATIONS={MAX_TOOL_ITERATIONS}")

    unique_images = []
    seen_urls = set()

    for image in image_results:
        if not isinstance(image, dict):
            continue

        image_url = image.get("url")
        if not image_url or image_url in seen_urls:
            continue

        seen_urls.add(image_url)
        unique_images.append({
            "url": image_url,
            "title": image.get("title", "")
        })

        if len(unique_images) >= 12:
            break

    seen_web = set()
    unique_web = []
    for s in web_sources:
        if s["url"] not in seen_web:
            seen_web.add(s["url"])
            unique_web.append(s)

    return {
        "text": final_text,
        "images": unique_images,
        "web_sources": unique_web[:20]
    }