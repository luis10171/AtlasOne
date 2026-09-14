"""Validation for the small JSON API used by the advisor pages."""

import json

from django.core.exceptions import RequestDataTooBig

MAX_CHAT_BODY_BYTES = 16_384
MAX_MESSAGE_CHARS = 2_000
TTS_VOICES = ("Kore", "Puck", "Fenrir", "Leda", "Zephyr", "Aoede")


def chat_payload(request, *, parent=False):
    if request.content_type != "application/json":
        raise ValueError("Content-Type must be application/json.")
    try:
        raw = request.body
        if len(raw) > MAX_CHAT_BODY_BYTES:
            raise ValueError("Request body is too large.")
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RequestDataTooBig) as exc:
        raise ValueError("Invalid JSON request body.") from exc
    if not isinstance(body, dict):
        raise ValueError("JSON body must be an object.")
    message = body.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Message must be a non-empty string.")
    message = message.strip()
    if len(message) > MAX_MESSAGE_CHARS:
        raise ValueError("Message must be 2,000 characters or fewer.")
    payload = {"message": message}
    if parent:
        student_id = body.get("student_id")
        if type(student_id) is not int or not 0 < student_id < 10**18:
            raise ValueError("student_id must be a positive integer.")
        enable_tts = body.get("enable_tts", False)
        if type(enable_tts) is not bool:
            raise ValueError("enable_tts must be a boolean.")
        voice = body.get("voice_name", "Kore")
        if not isinstance(voice, str) or voice not in TTS_VOICES:
            raise ValueError("Invalid TTS voice.")
        payload.update(student_id=student_id, enable_tts=enable_tts, voice_name=voice)
    return payload
