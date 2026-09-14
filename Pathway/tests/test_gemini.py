import json
import wave
from base64 import b64decode, b64encode
from io import BytesIO
from unittest import mock

from django.test import SimpleTestCase, override_settings

from Pathway.services.gemini import (
    _extract_candidate_text,
    _read_json,
    call_gemini_text,
    generate_tts_audio,
)


class GeminiTransportTests(SimpleTestCase):
    def test_credentials_are_in_header_and_response_is_bounded(self):
        body = {"candidates": [{"content": {"parts": [{"text": "Choose Geometry."}]}}]}
        response = mock.Mock()
        response.read.return_value = json.dumps(body).encode()
        with mock.patch("Pathway.services.gemini.request.urlopen") as network:
            network.return_value.__enter__.return_value = response
            answer = call_gemini_text(
                "test-key",
                "test-model",
                "System",
                "Context",
                [{"role": "user", "content": "Next class?"}],
            )
        request = network.call_args.args[0]
        self.assertNotIn("test-key", request.full_url)
        self.assertNotIn("?key=", request.full_url)
        self.assertEqual(request.get_header("X-goog-api-key"), "test-key")
        self.assertEqual(json.loads(request.data)["generationConfig"]["maxOutputTokens"], 1000)
        self.assertEqual(network.call_args.kwargs["timeout"], 15)
        response.read.assert_called_once_with(256 * 1024 + 1)
        self.assertEqual(answer, "Choose Geometry.")

    def test_malformed_provider_responses_raise_controlled_errors(self):
        for body in (
            {},
            {"candidates": [None]},
            {"candidates": [{"content": None}]},
            {"candidates": [{"content": {"parts": [{"text": 42}]}}]},
        ):
            with self.subTest(body=body):
                with self.assertRaises(ValueError):
                    _extract_candidate_text(body)

    def test_provider_size_limit(self):
        with self.assertRaisesMessage(ValueError, "size limit"):
            _read_json(BytesIO(b"x" * 101), max_bytes=100)
        with self.assertRaises(ValueError):
            _read_json(BytesIO(b"[]"), max_bytes=100)

    @override_settings(AI_ENABLED=True)
    def test_tts_wraps_pcm_as_wav_and_caps_text(self):
        pcm = b"\0\0" * 100
        body = {
            "candidates": [
                {"content": {"parts": [{"inlineData": {"data": b64encode(pcm).decode()}}]}}
            ]
        }
        with mock.patch("Pathway.services.gemini.request.urlopen") as network:
            network.return_value.__enter__.return_value.read.return_value = json.dumps(
                body
            ).encode()
            payload = generate_tts_audio("Word " * 500, api_key="test-key")
        sent = json.loads(network.call_args.args[0].data)
        self.assertLessEqual(len(sent["contents"][0]["parts"][0]["text"]), 750)
        network.assert_called_once()
        with wave.open(BytesIO(b64decode(payload["audio_base64"]))) as audio:
            self.assertEqual(audio.getframerate(), 24000)
            self.assertEqual(audio.readframes(100), pcm)

    @override_settings(AI_ENABLED=False)
    def test_disabled_speech_never_calls_provider(self):
        with mock.patch("Pathway.services.gemini.request.urlopen") as network:
            with self.assertRaisesMessage(ValueError, "disabled"):
                generate_tts_audio("Hello", api_key="test-key")
        network.assert_not_called()
