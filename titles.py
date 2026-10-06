"""
ApexGPT — titles.py
Generación de títulos de chat.
"""

from config import MODEL_NAME, ollama_client
from prompts import TITLE_PROMPT_TEMPLATE


def generate_chat_title(user_message: str, assistant_response: str) -> str:
    if not user_message or not user_message.strip():
        return "Nuevo chat"

    try:
        prompt = TITLE_PROMPT_TEMPLATE.format(
            user_message=user_message[:500],
            assistant_response=(assistant_response or "")[:300]
        )

        response = ollama_client.chat(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            options={"num_ctx": 2048}
        )

        title = (response.message.content or "").strip()
        title = title.strip('"\'`*#').strip()
        title = title.split("\n")[0].strip()
        title = title.rstrip(".。!?¡¿,")
        title = title[:60]

        if not title or len(title) < 2:
            fallback = user_message.strip().split("\n")[0]
            title = fallback[:40].strip() or "Nuevo chat"

        print(f"[title-gen] '{title}' <- de: '{user_message[:50]}...'")
        return title

    except Exception as e:
        print(f"[title-gen] Error: {e}")
        fallback = user_message.strip().split("\n")[0]
        return fallback[:40].strip() or "Nuevo chat"