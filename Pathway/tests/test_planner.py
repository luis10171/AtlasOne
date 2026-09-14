from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from Pathway.models import (
    CounselorConversation,
    Course,
    CourseRequest,
    District,
    GuidanceCounselor,
    Student,
    Subject,
    Transcript,
    TranscriptEntry,
)


class CounselorPlannerWorkflowTests(TestCase):
    def setUp(self):
        self.math = Subject.objects.create(name="Math")
        self.district = District.objects.create(name="Planner District", state="CA")
        self.prereq_course = Course.objects.create(
            name="Algebra I",
            subject=self.math,
            creditValue=1.0,
            instructor="Teacher A",
            isCoreClass=False,
        )
        self.next_course = Course.objects.create(
            name="Geometry",
            subject=self.math,
            creditValue=1.0,
            instructor="Teacher B",
            isCoreClass=False,
        )
        self.next_course.prerequisites.add(self.prereq_course)
        self.district.courses.add(self.prereq_course, self.next_course)

        self.student_user = User.objects.create_user(
            username="planner_student",
            password="StrongPass1!",
        )
        self.student = Student.objects.create(
            user=self.student_user,
            firstName="Planner",
            lastName="Student",
            gradeLevel=10,
            graduationYear=2028,
            GPA=3.0,
            district=self.district,
        )
        self.student_transcript = Transcript.objects.create(student=self.student)

        self.counselor_user = User.objects.create_user(
            username="counselor1",
            password="StrongPass1!",
            email="counselor1@example.com",
        )
        self.counselor = GuidanceCounselor.objects.create(
            user=self.counselor_user,
            firstName="Guidance",
            lastName="One",
            district=self.district,
        )

    def test_student_planner_redirects_for_senior(self):
        senior_user = User.objects.create_user(
            username="senior_student",
            password="StrongPass1!",
        )
        senior = Student.objects.create(
            user=senior_user,
            firstName="Senior",
            lastName="Student",
            gradeLevel=12,
            graduationYear=2026,
            GPA=2.9,
            district=self.district,
        )
        Transcript.objects.create(student=senior)

        self.client.login(username="senior_student", password="StrongPass1!")
        response = self.client.get(reverse("next_year_planner"))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("dashboard"))

    def test_student_can_submit_eligible_course_request(self):
        TranscriptEntry.objects.create(
            transcript=self.student_transcript,
            course=self.prereq_course,
            grade=88,
            creditsEarned=1.0,
            gradeTaken=9,
        )
        self.client.login(username="planner_student", password="StrongPass1!")
        response = self.client.post(
            reverse("next_year_planner"),
            {
                "course": self.next_course.id,
                "student_note": "I want to continue in math progression.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(CourseRequest.objects.count(), 1)
        course_request = CourseRequest.objects.get()
        self.assertEqual(course_request.status, CourseRequest.STATUS_PENDING)
        self.assertEqual(course_request.requested_for_grade, 11)

    def test_student_cannot_submit_blocked_course_request(self):
        self.client.login(username="planner_student", password="StrongPass1!")
        response = self.client.post(
            reverse("next_year_planner"),
            {
                "course": self.next_course.id,
                "student_note": "Please approve this class.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")
        self.assertEqual(CourseRequest.objects.count(), 0)

    def test_public_counselor_signup_cannot_grant_access(self):
        response = self.client.post(
            reverse("counselor_signup"),
            {
                "username": "new_counselor",
                "email": "new_counselor@example.com",
                "password": "StrongPass1!",
                "firstName": "New",
                "lastName": "Counselor",
                "district": str(self.district.id),
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(username="new_counselor").exists())

    def test_counselor_can_approve_course_request(self):
        TranscriptEntry.objects.create(
            transcript=self.student_transcript,
            course=self.prereq_course,
            grade=90,
            creditsEarned=1.0,
            gradeTaken=9,
        )
        course_request = CourseRequest.objects.create(
            student=self.student,
            course=self.next_course,
            requested_for_grade=11,
        )

        self.client.login(username="counselor1", password="StrongPass1!")
        response = self.client.post(
            reverse("review_course_request", args=[course_request.id]),
            {
                "decision": "approve",
                "counselor_note": "Approved because prerequisite is complete.",
            },
        )

        self.assertEqual(response.status_code, 302)
        course_request.refresh_from_db()
        self.assertEqual(course_request.status, CourseRequest.STATUS_APPROVED)
        self.assertEqual(course_request.reviewed_by, self.counselor)
        self.assertIn("Approved", course_request.counselor_note)

    def test_student_and_counselor_can_message_each_other(self):
        self.client.login(username="planner_student", password="StrongPass1!")
        response = self.client.post(
            reverse("student_messages"),
            {
                "counselor_id": str(self.counselor.id),
                "body": "Can you review my next-year options?",
            },
        )
        self.assertEqual(response.status_code, 302)

        conversation = CounselorConversation.objects.get(
            student=self.student,
            counselor=self.counselor,
        )
        self.assertEqual(conversation.messages.count(), 1)
        first_message = conversation.messages.first()
        self.assertEqual(first_message.sender, self.student_user)

        self.client.login(username="counselor1", password="StrongPass1!")
        response = self.client.post(
            reverse("counselor_messages_with_student", args=[self.student.id]),
            {
                "conversation_id": str(conversation.id),
                "body": "Yes, I can help. Please include your goals.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(conversation.messages.count(), 2)
        last_message = conversation.messages.last()
        self.assertEqual(last_message.sender, self.counselor_user)
