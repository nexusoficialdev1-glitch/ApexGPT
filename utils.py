"""
ApexGPT — utils.py
Utilidades varias.
"""

import base64


def validar_imagen_base64(image_base64: str):
    if not image_base64 or not isinstance(image_base64, str):
        return None

    if image_base64.startswith("data:"):
        try:
            image_base64 = image_base64.split(",", 1)[1]
        except IndexError:
            return None

    image_base64 = image_base64.strip().replace("\n", "").replace("\r", "")

    if len(image_base64) > 8 * 1024 * 1024:
        return None

    try:
        base64.b64decode(image_base64[:100] + "==")
    except Exception:
        return None

    return image_base64