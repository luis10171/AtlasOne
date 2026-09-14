import json
from io import StringIO
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from Pathway.models import (
    CounselorConversation,
    CounselorMessage,
    Course,
    CourseRequest,
    District,
    GuidanceCounselor,
    Parent,
    ParentCounselorConversation,
    ParentStudentLink,
    Student,
    Subject,
    Transcript,
    TranscriptEntry,
)
from Pathway.services.graduation import GraduationEngine
from Pathway.services.planner import build_next_year_planner
from Pathway.services.snapshot import build_student_academic_snapshot
from Pathway.utils.pdf_parser import extract_courses_from_pdf


@override_settings(AI_ENABLED=False)
class SecurityRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.district = District.objects.create(name="Test District", state="Demo")
        cls.other_district = District.objects.create(name="Other District", state="Demo")
        cls.counselor = GuidanceCounselor.objects.create(
            user=User.objects.create_user(username="counselor"),
            firstName="C",
            lastName="One",
            district=cls.district,
        )
        cls.other_counselor = GuidanceCounselor.objects.create(
            user=User.objects.create_user(username="other"),
            firstName="C",
            lastName="Two",
            district=cls.other_district,
        )
        cls.student = Student.objects.create(
            user=User.objects.create_user(username="student"),
            firstName="S",
            lastName="One",
            gradeLevel=10,
            graduationYear=timezone.now().year + 2,
            GPA=3.2,
            district=cls.district,
            assignedCounselor=cls.counselor,
        )
        cls.transcript = Transcript.objects.create(student=cls.student)
        cls.parent = Parent.objects.create(
            user=User.objects.create_user(username="parent"),
            firstName="P",
            lastName="One",
        )
        cls.link = ParentStudentLink.objects.create(parent=cls.parent, student=cls.student)
        cls.subject = Subject.objects.create(name="Math")
        cls.algebra = Course.objects.create(
            name="Algebra",
            subject=cls.subject,
            creditValue=1,
            instructor="Demo",
            isCoreClass=True,
        )
        cls.geometry = Course.objects.create(
            name="Geometry",
            subject=cls.subject,
            creditValue=1,
            instructor="Demo",
            isCoreClass=True,
        )
        cls.geometry.prerequisites.add(cls.algebra)
        cls.district.courses.add(cls.algebra, cls.geometry)

    def test_anonymous_dashboard_redirects_to_working_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, reverse("login") + "?next=/dashboard/")

    def test_student_cannot_message_another_district(self):
        self.client.force_login(self.student.user)
        response = self.client.post(
            reverse("student_messages"),
            {
                "counselor_id": self.other_counselor.id,
                "body": "Unauthorized",
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(CounselorMessage.objects.exists())

    def test_stale_student_thread_loses_access_after_transfer(self):
        thread = CounselorConversation.objects.create(
            student=self.student, counselor=self.counselor
        )
        CounselorMessage.objects.create(
            conversation=thread, sender=self.student.user, body="Private"
        )
        Student.objects.filter(pk=self.student.pk).update(
            district=self.other_district,
            assignedCounselor=None,
        )
        self.client.force_login(self.counselor.user)
        response = self.client.post(
            reverse("counselor_messages"),
            {
                "conversation_id": thread.pk,
                "body": "Unauthorized",
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(self.client.get(reverse("counselor_messages")), "Private")
        self.assertEqual(thread.messages.count(), 1)

    def test_removed_parent_link_revokes_existing_thread(self):
        thread = ParentCounselorConversation.objects.create(
            parent=self.parent,
            student=self.student,
            counselor=self.counselor,
        )
        self.link.delete()
        self.client.force_login(self.counselor.user)
        response = self.client.get(
            reverse("counselor_parent_messages_with_conversation", args=[thread.pk])
        )
        self.assertEqual(response.status_code, 404)
        self.client.force_login(self.parent.user)
        response = self.client.post(
            reverse("parent_ai_chatbot_message"),
            {"message": "Show grades", "student_id": self.student.pk},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_transcript_write_is_scoped(self):
        self.client.force_login(self.other_counselor.user)
        response = self.client.post(
            reverse("add_course", args=[self.student.pk]),
            {
                "course": self.algebra.pk,
                "grade": 90,
                "creditsEarned": 1,
                "gradeTaken": 9,
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(TranscriptEntry.objects.exists())

    def test_non_object_and_mistyped_json_never_reaches_provider(self):
        self.client.force_login(self.student.user)
        with mock.patch("Pathway.views.chat.generate_ai_advisor_reply") as provider:
            for payload in (
                [],
                None,
                42,
                {"message": []},
                {"message": None},
                {"message": "x" * 2001},
            ):
                with self.subTest(payload=type(payload).__name__):
                    response = self.client.post(
                        reverse("ai_chatbot_message"),
                        json.dumps(payload),
                        content_type="application/json",
                    )
                    self.assertEqual(response.status_code, 400)
            response = self.client.post(
                reverse("ai_chatbot_message"),
                b"\xff",
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 400)
            provider.assert_not_called()

    def test_parent_json_validates_id_boolean_and_voice(self):
        self.client.force_login(self.parent.user)
        for invalid in (
            {"student_id": True},
            {"student_id": {}},
            {"student_id": "abc"},
            {"enable_tts": "false"},
            {"voice_name": []},
        ):
            with self.subTest(invalid=invalid):
                payload = {"message": "Explain", "student_id": self.student.pk, **invalid}
                response = self.client.post(
                    reverse("parent_ai_chatbot_message"),
                    payload,
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 400)

    def test_chat_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.student.user)
        response = client.post(
            reverse("ai_chatbot_message"),
            {"message": "Hello"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_external_redirect_is_rejected(self):
        item = CourseRequest.objects.create(
            student=self.student,
            course=self.algebra,
            requested_for_grade=11,
        )
        self.client.force_login(self.counselor.user)
        response = self.client.post(
            reverse("review_course_request", args=[item.pk]),
            {
                "decision": "approve",
                "next": "https://example.invalid/phishing",
            },
        )
        self.assertRedirects(response, reverse("counselor_dashboard"))

    def test_signup_uses_password_validation_and_preserves_whitespace(self):
        fields = {
            "firstName": "New",
            "lastName": "Student",
            "email": "new@example.invalid",
            "username": "newstudent",
            "gradeLevel": 10,
            "graduationYear": timezone.now().year + 2,
            "password1": "12345678",
            "password2": "12345678",
        }
        response = self.client.post(reverse("signup"), fields)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="newstudent").exists())
        password = "  River-Orbit-92!  "
        response = self.client.post(
            reverse("signup"),
            {
                **fields,
                "password1": password,
                "password2": password,
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="newstudent")
        self.assertTrue(user.check_password(password))
        self.assertTrue(Transcript.objects.filter(student__user=user).exists())
        self.client.logout()
        self.assertEqual(
            self.client.post(
                reverse("login"),
                {
                    "username": "newstudent",
                    "password": password,
                },
            ).status_code,
            302,
        )

    def test_signup_rolls_back_user_if_profile_creation_fails(self):
        fields = {
            "firstName": "New",
            "lastName": "Student",
            "email": "new@example.invalid",
            "username": "rollback",
            "gradeLevel": 10,
            "graduationYear": timezone.now().year + 2,
            "password1": "River-Orbit-92!",
            "password2": "River-Orbit-92!",
        }
        with mock.patch(
            "Pathway.forms.Transcript.objects.create", side_effect=RuntimeError("failure")
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("signup"), fields)
        self.assertFalse(User.objects.filter(username="rollback").exists())

    def test_passing_threshold_agrees_across_services(self):
        for grade in (59, 60, 64, 65):
            with self.subTest(grade=grade):
                entry = TranscriptEntry.objects.create(
                    transcript=self.transcript,
                    course=self.algebra,
                    grade=grade,
                    creditsEarned=1,
                    gradeTaken=9,
                )
                planner = build_next_year_planner(self.student)
                snapshot = build_student_academic_snapshot(self.student)
                expected = grade >= 60
                self.assertEqual(self.algebra.pk in planner["passed_ids"], expected)
                self.assertEqual(snapshot["taken_courses"][0]["status"] == "completed", expected)
                report = GraduationEngine(self.student).build_progress_report()
                algebra = next(c for c in report["core_requirements"] if c["name"] == "Algebra")
                self.assertEqual(algebra["completed"], expected)
                entry.delete()

    @mock.patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected network request"))
    def test_offline_demo_does_not_call_provider(self, network):
        self.client.force_login(self.student.user)
        response = self.client.post(
            reverse("ai_chatbot_message"),
            {"message": "Which class next?"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("response", response.json())
        network.assert_not_called()

    def test_unknown_pdf_numbers_remain_blank_for_review(self):
        page = mock.Mock()
        page.extract_tables.return_value = [[["Algebra", "", "N/A", "", "1"]]]
        with mock.patch("Pathway.utils.pdf_parser.pdfplumber.open") as open_pdf:
            open_pdf.return_value.__enter__.return_value.pages = [page]
            result = extract_courses_from_pdf(
                SimpleUploadedFile("transcript.pdf", b"%PDF-test"),
                self.student,
                [self.algebra],
            )
        self.assertIsNone(result[0]["grade"])
        self.assertIsNone(result[0]["credits"])

    def test_oversized_pdf_is_rejected_instead_of_truncated(self):
        with mock.patch("Pathway.utils.pdf_parser.pdfplumber.open") as open_pdf:
            open_pdf.return_value.__enter__.return_value.pages = [mock.Mock()] * 21
            with self.assertRaisesMessage(ValueError, "at most 20 pages"):
                extract_courses_from_pdf(
                    SimpleUploadedFile("transcript.pdf", b"%PDF-test"),
                    self.student,
                    [self.algebra],
                )

    def test_seed_does_not_overwrite_existing_accounts(self):
        with override_settings(DEBUG=True):
            with self.assertRaises(CommandError):
                call_command("seed_demo", stdout=StringIO())
        self.assertEqual(User.objects.count(), 4)

    def test_demo_seed_refuses_production(self):
        with override_settings(DEBUG=False):
            with self.assertRaises(CommandError):
                call_command("seed_demo", stdout=StringIO())
