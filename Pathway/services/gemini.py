"""Gemini transport, response parsing, and optional speech generation."""

import json
import os
import wave
from base64 import b64decode, b64encode
from io import BytesIO
from urllib import request

from django.conf import settings

DEFAULT_GEMINI_TEXT_MODEL = "gemini-2.5-flash-lite"
DEFAULT_GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"


def _build_gemini_contents(context_message, messages):
    contents = [{"role": "user", "parts": [{"text": context_message}]}]
    for message in messages:
        role = message.get("role")
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        if role in {"system", "developer"}:
            # Gemini system instructions are sent separately.
            continue
        gemini_role = "model" if role == "assistant" else "user"
        contents.append({"role": gemini_role, "parts": [{"text": content}]})
    return contents


def _candidate_parts(body):
    candidates = body.get("candidates")
    if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
        raise ValueError("Gemini returned no candidates.")
    content = candidates[0].get("content")
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list) or not all(isinstance(part, dict) for part in parts):
        raise ValueError("Gemini returned invalid content parts.")
    return parts


def _extract_candidate_text(body):
    parts = _candidate_parts(body)
    text_parts = [part["text"] for part in parts if isinstance(part.get("text"), str)]
    answer = "\n".join(part for part in text_parts if part).strip()
    if not answer:
        raise ValueError("Gemini returned an empty response.")
    return answer


def call_gemini_text(
    api_key,
    model,
    system_prompt,
    context_message,
    messages,
    temperature=0.4,
):
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": _build_gemini_contents(context_message, messages),
        "generationConfig": {"temperature": temperature, "maxOutputTokens": 1000},
    }
    http_request = request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    with request.urlopen(http_request, timeout=settings.AI_TEXT_TIMEOUT_SECONDS) as response:
        body = _read_json(response, max_bytes=256 * 1024)

    return _extract_candidate_text(body)


def _pcm_to_wav_bytes(pcm_bytes, sample_rate=24000, channels=1, sample_width=2):
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return buffer.getvalue()


def _compact_text_for_tts(text, max_chars):
    compact = " ".join(str(text).split())
    if len(compact) <= max_chars:
        return compact

    truncated = compact[:max_chars]
    floor = int(max_chars * 0.6)
    for marker in [". ", "! ", "? ", "; ", ", "]:
        idx = truncated.rfind(marker)
        if idx >= floor:
            return truncated[: idx + 1].strip()
    return truncated.strip()


def generate_tts_audio_base64(
    text,
    voice_name="Kore",
    api_key=None,
    model=None,
    timeout_seconds=None,
):
    if not settings.AI_ENABLED:
        raise ValueError("Speech is disabled.")
    if not text:
        raise ValueError("Text is required for TTS generation.")

    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    model = model or os.environ.get("GEMINI_TTS_MODEL", DEFAULT_GEMINI_TTS_MODEL)
    if not api_key:
        raise ValueError("Gemini API key not configured.")

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": text,
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": voice_name,
                    }
                }
            },
        },
    }
    http_request = request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    with request.urlopen(
        http_request, timeout=timeout_seconds or settings.AI_TTS_TIMEOUT_SECONDS
    ) as response:
        body = _read_json(response, max_bytes=4 * 1024 * 1024)

    parts = _candidate_parts(body)
    inline_part = next(
        (
            part
            for part in parts
            if isinstance(part.get("inlineData"), dict)
            and isinstance(part["inlineData"].get("data"), str)
            and part["inlineData"]["data"]
        ),
        None,
    )
    if not inline_part:
        raise ValueError("Gemini TTS returned no audio payload.")

    encoded_audio = inline_part["inlineData"]["data"]
    pcm_bytes = b64decode(encoded_audio, validate=True)
    wav_bytes = _pcm_to_wav_bytes(pcm_bytes)
    return {
        "audio_base64": b64encode(wav_bytes).decode("utf-8"),
        "audio_mime_type": "audio/wav",
    }


def generate_tts_audio(text, voice_name="Kore", api_key=None, model=None):
    """One bounded attempt; retrying inside the request multiplies worker latency."""
    return generate_tts_audio_base64(
        _compact_text_for_tts(text, 750),
        voice_name=voice_name,
        api_key=api_key,
        model=model,
    )


def _read_json(response, max_bytes):
    raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("Provider response exceeded the size limit.")
    body = json.loads(raw.decode("utf-8"))
    if not isinstance(body, dict):
        raise ValueError("Provider response must be a JSON object.")
    return body
