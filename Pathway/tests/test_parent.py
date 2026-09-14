from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from Pathway.models import (
    District,
    GuidanceCounselor,
    Parent,
    ParentCounselorConversation,
    ParentStudentLink,
    Student,
    Subject,
    Transcript,
)
from Pathway.services.advisor_reply import AdvisorReply


class ParentRoleWorkflowTests(TestCase):
    def setUp(self):
        self.math = Subject.objects.create(name="Math")
        self.district = District.objects.create(name="Family District", state="CA")
        self.counselor_user = User.objects.create_user(
            username="family_counselor",
            password="StrongPass1!",
        )
        self.counselor = GuidanceCounselor.objects.create(
            user=self.counselor_user,
            firstName="Family",
            lastName="Counselor",
            district=self.district,
        )

        self.student_user_1 = User.objects.create_user(
            username="family_student_1",
            password="StrongPass1!",
        )
        self.student_1 = Student.objects.create(
            user=self.student_user_1,
            firstName="Kid",
            lastName="One",
            gradeLevel=9,
            graduationYear=2029,
            GPA=3.3,
            district=self.district,
            assignedCounselor=self.counselor,
        )
        Transcript.objects.create(student=self.student_1)

        self.student_user_2 = User.objects.create_user(
            username="family_student_2",
            password="StrongPass1!",
        )
        self.student_2 = Student.objects.create(
            user=self.student_user_2,
            firstName="Kid",
            lastName="Two",
            gradeLevel=10,
            graduationYear=2028,
            GPA=3.1,
            district=self.district,
            assignedCounselor=self.counselor,
        )
        Transcript.objects.create(student=self.student_2)

    def test_public_parent_signup_cannot_claim_students(self):
        response = self.client.post(
            reverse("parent_signup"),
            {
                "username": "parent1",
                "email": "parent1@example.com",
                "password": "StrongPass1!",
                "firstName": "Parent",
                "lastName": "One",
                "preferredLanguage": "Spanish",
                "relationship": "guardian",
                "studentUsernames": f"{self.student_user_1.username}, {self.student_user_2.username}",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(username="parent1").exists())
        self.assertFalse(ParentStudentLink.objects.exists())

    def test_parent_signup_rejects_unknown_student_username(self):
        response = self.client.post(
            reverse("parent_signup"),
            {
                "username": "parent_unknown",
                "email": "parent_unknown@example.com",
                "password": "StrongPass1!",
                "firstName": "Parent",
                "lastName": "Unknown",
                "relationship": "guardian",
                "studentUsernames": "missing_student_username",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(username="parent_unknown").exists())

    def test_parent_dashboard_requires_linked_student_access(self):
        parent_user = User.objects.create_user(
            username="linked_parent",
            password="StrongPass1!",
        )
        parent = Parent.objects.create(
            user=parent_user,
            firstName="Linked",
            lastName="Parent",
        )
        ParentStudentLink.objects.create(
            parent=parent, student=self.student_1, relationship="guardian"
        )

        self.client.login(username="linked_parent", password="StrongPass1!")
        response = self.client.get(
            reverse("parent_dashboard"),
            {"student": self.student_2.id},
        )
        self.assertEqual(response.status_code, 404)

    def test_parent_and_counselor_can_exchange_messages(self):
        parent_user = User.objects.create_user(
            username="msg_parent",
            password="StrongPass1!",
        )
        parent = Parent.objects.create(
            user=parent_user,
            firstName="Message",
            lastName="Parent",
        )
        ParentStudentLink.objects.create(
            parent=parent, student=self.student_1, relationship="mother"
        )

        self.client.login(username="msg_parent", password="StrongPass1!")
        response = self.client.post(
            reverse("parent_messages_with_student", args=[self.student_1.id]),
            {"body": "Can we review graduation planning in simple terms?"},
        )
        self.assertEqual(response.status_code, 302)

        conversation = ParentCounselorConversation.objects.get(
            parent=parent,
            student=self.student_1,
            counselor=self.counselor,
        )
        self.assertEqual(conversation.messages.count(), 1)
        first_message = conversation.messages.first()
        self.assertEqual(first_message.sender, parent_user)

        self.client.login(username="family_counselor", password="StrongPass1!")
        response = self.client.post(
            reverse("counselor_parent_messages_with_conversation", args=[conversation.id]),
            {
                "conversation_id": str(conversation.id),
                "body": "Yes. I will break the plan into simple weekly actions.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(conversation.messages.count(), 2)
        last_message = conversation.messages.last()
        self.assertEqual(last_message.sender, self.counselor_user)

    @mock.patch("Pathway.views.chat.generate_tts_audio")
    @mock.patch("Pathway.views.chat.generate_parent_ai_reply")
    def test_parent_ai_chatbot_message_supports_tts(
        self,
        mock_parent_ai_reply,
        mock_generate_tts,
    ):
        parent_user = User.objects.create_user(
            username="ai_parent",
            password="StrongPass1!",
        )
        parent = Parent.objects.create(
            user=parent_user,
            firstName="AI",
            lastName="Parent",
            preferredLanguage="Arabic",
        )
        ParentStudentLink.objects.create(
            parent=parent, student=self.student_1, relationship="guardian"
        )

        mock_parent_ai_reply.return_value = AdvisorReply(
            "Here is a simple explanation and next steps.",
            {"graduation_status": {"status": "On Track", "completion_percent": 72}},
        )
        mock_generate_tts.return_value = {
            "audio_base64": "UklGRmR1bW15",
            "audio_mime_type": "audio/wav",
        }

        self.client.login(username="ai_parent", password="StrongPass1!")
        response = self.client.post(
            reverse("parent_ai_chatbot_message"),
            data={
                "message": "Please explain in Arabic.",
                "student_id": self.student_1.id,
                "enable_tts": True,
                "voice_name": "Kore",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("response", payload)
        self.assertIn("audio_base64", payload)
        mock_parent_ai_reply.assert_called_once()
        mock_generate_tts.assert_called_once()
