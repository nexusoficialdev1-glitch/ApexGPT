"""
ApexGPT — server.py
Backend del chatbot. Solo Flask + endpoints.
"""

import os
import uuid
import time
import traceback

from flask import Flask, request, jsonify
from flask_cors import CORS

from config import (
    MODEL_NAME,
    OLLAMA_API_KEY,
    HF_API_TOKEN,
    HF_MODEL_NAME,
    D1_API_URL,
    D1_API_SECRET,
)
from prompts import APEXGPT_SYSTEM_PROMPT  # noqa: F401 (referencia)
from memory import (
    init_memory_db,
    get_user_memories,
    save_user_memory,
    delete_user_memory,
    delete_all_user_memories,
    extract_memories_from_conversation,
)
from agent import build_messages, run_agent
from imagegen import parse_image_request, generate_image_hf
from titles import generate_chat_title
from utils import validar_imagen_base64


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB


# ============================================================
# CORS
# ============================================================

_allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "").strip()

if _allowed_origins_env:
    _origins = [o.strip() for o in _allowed_origins_env.split(",") if o.strip()]
    CORS(app, origins=_origins)
    print(f"CORS configurado para: {_origins}")
else:
    print("ADVERTENCIA: ALLOWED_ORIGINS no configurada, CORS abierto a '*'.")
    CORS(app)


# ============================================================
# INIT DB
# ============================================================

init_memory_db()


# ============================================================
# API CHAT
# ============================================================

@app.route("/api/chat", methods=["POST"])
def api_chat():
    try:
        data = request.get_json(force=True) or {}

        history = data.get("history")

        if not history:
            single_message = (data.get("message") or "").strip()
            if single_message:
                history = [{"role": "user", "content": single_message}]
            else:
                history = []

        # Copia profunda ligera para no mutar el payload original
        history = [dict(m) for m in history]

        custom_instructions = data.get("custom_instructions", {})
        uid = data.get("uid")

        user_memories = get_user_memories(uid) if uid else []

        raw_image = data.get("image_base64")
        user_image_base64 = validar_imagen_base64(raw_image) if raw_image else None

        if raw_image and not user_image_base64:
            print("[api_chat] Imagen base64 rechazada (inválida o demasiado grande)")

        file_name = data.get("file_name")
        file_text = data.get("file_text")

        if file_text and isinstance(file_text, str):
            if len(file_text) > 100_000:
                file_text = file_text[:100_000] + "\n\n[...archivo truncado...]"

        print(
            f"[api_chat] history len={len(history)} "
            f"imagen={'sí' if user_image_base64 else 'no'} "
            f"archivo={file_name or 'no'} "
            f"uid={uid} recuerdos={len(user_memories)} "
            f"deep_thinking={custom_instructions.get('deep_thinking', False)} "
            f"smart_search={custom_instructions.get('smart_search', False)}"
        )

        if not history:
            return jsonify({
                "success": False,
                "message": "No hay mensajes para procesar"
            }), 400

        if file_text and file_name and history:
            last = history[-1]
            if last.get("role") == "user":
                original = str(last.get("content", "")).strip()
                last["content"] = (
                    f"[El usuario adjuntó un archivo llamado \"{file_name}\"]\n\n"
                    f"Contenido del archivo:\n"
                    f"```\n{file_text}\n```\n\n"
                    f"---\n\n"
                    f"Mensaje del usuario: {original}"
                )

        messages = build_messages(
            history,
            custom_instructions,
            user_image_base64=user_image_base64,
            memories=user_memories
        )

        result = run_agent(messages)

        text = (result.get("text") or "").strip()

        print(f"[api_chat] respuesta len={len(text)} "
              f"imágenes={len(result.get('images', []))} "
              f"fuentes={len(result.get('web_sources', []))}")

        if not text:
            return jsonify({
                "success": False,
                "message": (
                    "El modelo no generó respuesta. "
                    "Verifica OLLAMA_API_KEY, el nombre del modelo "
                    "y que el servicio de Ollama Cloud esté disponible."
                ),
                "response": "",
                "images": result.get("images", []),
                "web_sources": result.get("web_sources", [])
            }), 502

        generated_image_url = None
        image_error = None

        parsed = parse_image_request(text)
        if parsed and len(parsed) == 3 and parsed[0] is not None:
            img_prompt, img_style, cleaned_text = parsed
            print(f"[api_chat] Generando imagen: prompt='{img_prompt[:60]}' estilo={img_style}")
            generated_image_url, image_error = generate_image_hf(img_prompt, img_style)

            if generated_image_url:
                text = cleaned_text or "Aquí tienes tu imagen."
            else:
                text = cleaned_text or text
                if image_error:
                    text += f"\n\n_(No pude generar la imagen: {image_error})_"

        memories_saved = []
        if uid and history:
            try:
                last_user = ""
                for m in reversed(history):
                    if m.get("role") == "user":
                        last_user = m.get("content", "")
                        break

                if last_user and text:
                    nuevos = extract_memories_from_conversation(last_user, text)
                    for mem in nuevos:
                        save_user_memory(uid, mem)
                        memories_saved.append(mem.get("text"))
                    if nuevos:
                        print(f"[Memory] {len(nuevos)} recuerdos nuevos para {uid}")
            except Exception as e:
                print(f"[Memory] Error en auto-aprendizaje: {e}")

        response_payload = {
            "success": True,
            "response": text,
            "images": result.get("images", []),
            "web_sources": result.get("web_sources", []),
            "memories_saved": memories_saved
        }

        if generated_image_url:
            response_payload["generated_image"] = generated_image_url

        return jsonify(response_payload)

    except Exception as error:
        print("Error en /api/chat:", repr(error))
        traceback.print_exc()
        return jsonify({
            "success": False,
            "message": f"Error interno: {error}"
        }), 500


# ============================================================
# API — GENERAR TÍTULO
# ============================================================

@app.route("/api/generate-title", methods=["POST"])
def api_generate_title():
    try:
        data = request.get_json(force=True) or {}
        user_message = (data.get("user_message") or "").strip()
        assistant_response = (data.get("assistant_response") or "").strip()

        if not user_message:
            return jsonify({"success": False, "message": "Falta 'user_message'"}), 400

        title = generate_chat_title(user_message, assistant_response)
        return jsonify({"success": True, "title": title})

    except Exception as e:
        print(f"[generate-title] Error: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500


# ============================================================
# API — MEMORIA
# ============================================================

@app.route("/api/memory/<uid>", methods=["GET"])
def api_get_memory(uid):
    memories = get_user_memories(uid)
    return jsonify({"success": True, "memories": memories})


@app.route("/api/memory/<uid>", methods=["POST"])
def api_add_memory(uid):
    try:
        data = request.get_json(force=True) or {}
        text = (data.get("text") or "").strip()
        category = data.get("category", "otro")

        if not text:
            return jsonify({"success": False, "message": "Falta el texto"}), 400

        memory_obj = {
            "id": str(uuid.uuid4()),
            "text": text[:300],
            "category": category,
            "created_at": int(time.time()),
            "source": "manual"
        }
        save_user_memory(uid, memory_obj)
        return jsonify({"success": True, "memory": memory_obj})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/memory/<uid>/<memory_id>", methods=["DELETE"])
def api_delete_memory(uid, memory_id):
    ok = delete_user_memory(uid, memory_id)
    return jsonify({"success": ok})


@app.route("/api/memory/<uid>/all", methods=["DELETE"])
def api_delete_all_memory(uid):
    ok = delete_all_user_memories(uid)
    return jsonify({"success": ok})


# ============================================================
# API — GENERAR IMAGEN DIRECTA
# ============================================================

@app.route("/api/generate-image", methods=["POST"])
def api_generate_image():
    try:
        data = request.get_json(force=True) or {}
        prompt = (data.get("prompt") or "").strip()
        style = (data.get("style") or "none").strip().lower()

        if not prompt:
            return jsonify({"success": False, "message": "Falta el campo 'prompt'"}), 400

        data_url, error = generate_image_hf(prompt, style)

        if error:
            return jsonify({"success": False, "message": error}), 500

        return jsonify({
            "success": True,
            "image_base64": data_url,
            "prompt": prompt,
            "style": style
        })

    except Exception as e:
        print(f"[generate-image] Error: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "ApexGPT Chat API",
        "model": MODEL_NAME,
        "ollama_key_set": bool(OLLAMA_API_KEY),
        "image_generation": bool(HF_API_TOKEN),
        "image_model": HF_MODEL_NAME,
        "d1_api_url": D1_API_URL or "(no configurado)",
        "d1_configured": bool(D1_API_URL and D1_API_SECRET),
    })


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)