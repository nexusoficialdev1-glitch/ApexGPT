"""
ApexGPT — imagegen.py
Generación de imágenes con Hugging Face.
"""

import io
import re
import base64
import traceback

from config import HF_API_TOKEN, HF_MODEL_NAME, get_hf_client


IMAGE_REQUEST_REGEX = re.compile(
    r"\[GENERAR_IMAGEN:\s*(.+?)\|([\w]+)\s*\]",
    re.IGNORECASE | re.DOTALL
)


IMAGE_STYLES = {
    "none": "{prompt}",
    "realistic": (
        "A hyper-realistic, high-detail photograph of {prompt}, "
        "8k resolution, cinematic lighting, sharp focus, professional photography"
    ),
    "anime": (
        "Anime style artwork of {prompt}, vibrant colors, "
        "studio quality, detailed illustration, cel-shaded"
    ),
    "digital": (
        "Digital art of {prompt}, concept art, highly detailed, "
        "vibrant colors, trending on ArtStation"
    ),
    "minimalist": (
        "Minimalist illustration of {prompt}, clean lines, "
        "simple background, flat design, modern aesthetic"
    ),
    "3d": (
        "3D render of {prompt}, Octane render, soft lighting, "
        "high detail, Pixar style, cinematic"
    ),
    "cartoon": (
        "Cartoon illustration of {prompt}, bold outlines, "
        "vibrant flat colors, playful style"
    ),
}


def parse_image_request(text: str):
    if not text:
        return None, None, None

    match = IMAGE_REQUEST_REGEX.search(text)
    if not match:
        return None, None, None

    prompt = match.group(1).strip()
    style = match.group(2).strip().lower()
    cleaned_text = IMAGE_REQUEST_REGEX.sub("", text).strip()

    if not prompt:
        return None, None, None

    return (prompt, style, cleaned_text)


def generate_image_hf(prompt: str, style: str = "none"):
    if not HF_API_TOKEN:
        return None, "Generación de imágenes no configurada en el servidor."

    template = IMAGE_STYLES.get(style, IMAGE_STYLES["none"])
    final_prompt = template.format(prompt=prompt)[:500]

    try:
        client = get_hf_client()

        image = client.text_to_image(
            final_prompt,
            model=HF_MODEL_NAME,
        )

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

        if not image_bytes or len(image_bytes) < 100:
            return None, "Hugging Face devolvió una imagen vacía."

        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:image/png;base64,{image_base64}"

        print(f"[image-gen] '{prompt[:60]}' OK: {len(image_bytes)} bytes, estilo={style}")
        return data_url, None

    except Exception as e:
        print(f"[image-gen] Error: {e}")
        traceback.print_exc()

        error_str = str(e).lower()

        if "401" in error_str or "unauthorized" in error_str or "invalid" in error_str:
            return None, (
                "Token de Hugging Face inválido o sin permisos. "
                "Verifica que tenga 'Make calls to Inference Providers'."
            )

        if "403" in error_str or "forbidden" in error_str:
            return None, "Tu token no tiene acceso a este modelo."

        if "429" in error_str or "rate limit" in error_str:
            return None, "Límite de peticiones alcanzado. Espera unos minutos."

        if "410" in error_str or "deprecated" in error_str:
            return None, (
                f"El modelo '{HF_MODEL_NAME}' fue deprecado. "
                "Cambia la variable HF_MODEL en Render."
            )

        return None, f"Error generando imagen: {e}"