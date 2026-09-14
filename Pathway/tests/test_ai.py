import os
from http.client import IncompleteRead
from unittest import mock
from urllib.error import HTTPError, URLError

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from Pathway.models import (
    Course,
    District,
    GraduationRequirement,
    Parent,
    ParentStudentLink,
    Student,
    Subject,
    Transcript,
)
from Pathway.services.ai_advisor import (
    generate_ai_advisor_reply,
)
from Pathway.services.parent_ai_advisor import generate_parent_ai_reply


@override_settings(
    AI_ENABLED=True,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
@mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
class AIFallbackLocalizationTests(TestCase):
    def setUp(self):
        self.math = Subject.objects.create(name="Math")
        self.district = District.objects.create(name="Localization District", state="CA")
        self.course = Course.objects.create(
            name="Algebra I",
            subject=self.math,
            creditValue=1.0,
            instructor="Teacher L",
            isCoreClass=True,
        )
        self.district.courses.add(self.course)
        GraduationRequirement.objects.create(
            district=self.district,
            subject=self.math,
            requiredCredits=2.0,
        )

        self.student_user = User.objects.create_user(
            username="locale_student",
            password="StrongPass1!",
        )
        self.student = Student.objects.create(
            user=self.student_user,
            firstName="Locale",
            lastName="Student",
            gradeLevel=10,
            graduationYear=2028,
            GPA=3.0,
            district=self.district,
        )
        Transcript.objects.create(student=self.student)

        self.parent_user = User.objects.create_user(
            username="locale_parent",
            password="StrongPass1!",
        )
        self.parent = Parent.objects.create(
            user=self.parent_user,
            firstName="Locale",
            lastName="Parent",
            preferredLanguage="Spanish",
        )
        ParentStudentLink.objects.create(parent=self.parent, student=self.student)

    def chat_cases(self):
        return (
            (
                self.student_user,
                "ai_chatbot_message",
                {"message": "Which course next?"},
                f"ai_chat_history_v2_{self.student.pk}",
                "Pathway.services.ai_advisor._call_gemini",
                "Pathway.services.ai_advisor",
            ),
            (
                self.parent_user,
                "parent_ai_chatbot_message",
                {"message": "Which course next?", "student_id": self.student.pk},
                f"parent_ai_chat_history_v2_{self.parent.pk}_{self.student.pk}",
                "Pathway.services.parent_ai_advisor.call_gemini_text",
                "Pathway.services.parent_ai_advisor",
            ),
        )

    def test_successful_replies_have_no_failure_status(self):
        for user, route, body, history_key, target, _ in self.chat_cases():
            with self.subTest(route=route), mock.patch(target, return_value="Choose Algebra."):
                self.client.force_login(user)
                response = self.client.post(reverse(route), body, content_type="application/json")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["response"], "Choose Algebra.")
                self.assertIs(response.json()["api_failed"], False)
                self.assertEqual(
                    self.client.session[history_key][-1],
                    {"role": "assistant", "content": "Choose Algebra."},
                )

    def test_all_provider_failures_mark_only_the_failed_reply(self):
        failures = [
            HTTPError("https://example.invalid", status, "private-provider-detail", {}, None)
            for status in (400, 401, 403, 429, 500, 503)
        ] + [
            URLError("private-provider-detail"),
            TimeoutError("private-provider-detail"),
            ConnectionResetError("private-provider-detail"),
            IncompleteRead(b"private-provider-detail"),
            ValueError("private-provider-detail"),
            RuntimeError("private-provider-detail"),
        ]
        for user, route, body, history_key, target, logger in self.chat_cases():
            self.client.force_login(user)
            for failure in failures:
                with self.subTest(route=route, failure=repr(failure)):
                    with mock.patch(target, side_effect=failure), self.assertLogs(logger) as logs:
                        response = self.client.post(
                            reverse(route), body, content_type="application/json"
                        )
                    self.assertEqual(response.status_code, 200)
                    self.assertIs(response.json()["api_failed"], True)
                    self.assertNotIn("private-provider-detail", response.content.decode())
                    self.assertNotIn("private-provider-detail", " ".join(logs.output))
                    history = self.client.session[history_key]
                    self.assertEqual(history[-1]["content"], response.json()["response"])
                    self.assertNotIn("api_failed", history[-1])
                    self.assertNotIn("AI service unavailable", str(history))
                    with mock.patch(target, return_value="Choose Algebra.") as provider:
                        recovered = self.client.post(
                            reverse(route), body, content_type="application/json"
                        )
                    self.assertIs(recovered.json()["api_failed"], False)
                    sent_history = (
                        provider.call_args.kwargs["messages"]
                        if provider.call_args.kwargs
                        else provider.call_args.args[3]
                    )
                    self.assertNotIn("AI service unavailable", str(sent_history))
                    self.assertNotIn("api_failed", str(sent_history))

    def test_disabled_ai_or_missing_key_is_not_a_failed_request(self):
        for enabled, key in ((False, "test-key"), (True, "")):
            for user, route, body, _, target, _ in self.chat_cases():
                with (
                    self.subTest(route=route, enabled=enabled, key_present=bool(key)),
                    override_settings(AI_ENABLED=enabled),
                    mock.patch.dict(os.environ, {"GEMINI_API_KEY": key}),
                    mock.patch(target) as provider,
                ):
                    self.client.force_login(user)
                    response = self.client.post(
                        reverse(route), body, content_type="application/json"
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertIs(response.json()["api_failed"], False)
                    provider.assert_not_called()

    def test_legacy_status_text_is_not_sent_back_to_gemini(self):
        for user, route, body, history_key, target, _ in self.chat_cases():
            with (
                self.subTest(route=route),
                mock.patch(target, return_value="Choose Algebra.") as provider,
            ):
                self.client.force_login(user)
                session = self.client.session
                session[history_key.replace("_v2_", "_")] = [
                    {
                        "role": "assistant",
                        "content": "YOU ARE CURRENTLY OFFLINE. Fallback message:Hi",
                    }
                ]
                session.save()
                response = self.client.post(reverse(route), body, content_type="application/json")
                self.assertEqual(response.status_code, 200)
                sent_history = (
                    provider.call_args.kwargs["messages"]
                    if provider.call_args.kwargs
                    else provider.call_args.args[3]
                )
                self.assertEqual(sent_history, [{"role": "user", "content": body["message"]}])

    @mock.patch("Pathway.views.chat.generate_tts_audio", side_effect=ValueError("Speech failed"))
    @mock.patch(
        "Pathway.services.parent_ai_advisor.call_gemini_text", return_value="Choose Algebra."
    )
    def test_speech_failure_does_not_mark_successful_text_as_offline(self, provider, speech):
        self.client.force_login(self.parent_user)
        response = self.client.post(
            reverse("parent_ai_chatbot_message"),
            {"message": "Next class?", "student_id": self.student.pk, "enable_tts": True},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["api_failed"], False)
        self.assertIn("tts_error", response.json())
        speech.assert_called_once_with("Choose Algebra.", voice_name="Kore")

    @mock.patch("Pathway.services.ai_advisor._call_gemini")
    def test_student_translation_fallback_is_localized_and_not_key_error(
        self,
        mock_call_gemini,
    ):
        mock_call_gemini.side_effect = ValueError("Gemini response parse error")

        result = generate_ai_advisor_reply(
            self.student,
            "Explain this for my parents in Spanish.",
            [],
        )

        self.assertIn("Resumen para familias", result.text)
        self.assertNotIn("GEMINI_API_KEY", result.text)
        self.assertTrue(result.api_failed)

    @mock.patch("Pathway.services.parent_ai_advisor.call_gemini_text")
    def test_parent_fallback_uses_preferred_language_when_model_fails(
        self,
        mock_call_gemini_text,
    ):
        mock_call_gemini_text.side_effect = ValueError("Gemini response parse error")

        result = generate_parent_ai_reply(
            self.parent,
            self.student,
            "Can you explain this simply?",
            [],
        )

        self.assertIn("Aqui tienes una actualizacion simple", result.text)
        self.assertTrue(result.api_failed)
