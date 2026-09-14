from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from Pathway.models import (
    Course,
    CourseRequest,
    District,
    GuidanceCounselor,
    Student,
    Subject,
    Transcript,
)


class CounselorAuthorizationTests(TestCase):
    """Regression coverage for district boundaries around student records."""

    def setUp(self):
        subject = Subject.objects.create(name="Math")
        self.counselor_district = District.objects.create(name="Counselor District", state="CA")
        other_district = District.objects.create(name="Other District", state="NY")
        course = Course.objects.create(
            name="Algebra I",
            subject=subject,
            creditValue=1.0,
            instructor="Teacher",
            isCoreClass=True,
        )
        self.counselor_district.courses.add(course)
        other_district.courses.add(course)

        counselor_user = User.objects.create_user(
            username="scoped_counselor", password="StrongPass1!"
        )
        self.counselor = GuidanceCounselor.objects.create(
            user=counselor_user,
            firstName="Scoped",
            lastName="Counselor",
            district=self.counselor_district,
        )
        student_user = User.objects.create_user(username="other_student", password="StrongPass1!")
        self.other_student = Student.objects.create(
            user=student_user,
            firstName="Other",
            lastName="Student",
            gradeLevel=10,
            graduationYear=2028,
            GPA=3.0,
            district=other_district,
        )
        Transcript.objects.create(student=self.other_student)
        self.course_request = CourseRequest.objects.create(
            student=self.other_student,
            course=course,
            requested_for_grade=11,
        )

    def test_counselor_cannot_view_or_review_other_district_student(self):
        self.client.login(username="scoped_counselor", password="StrongPass1!")

        profile_response = self.client.get(
            reverse("counselor_student_profile", args=[self.other_student.id])
        )
        review_response = self.client.post(
            reverse("review_course_request", args=[self.course_request.id]),
            {"decision": "approve"},
        )

        self.assertEqual(profile_response.status_code, 404)
        self.assertEqual(review_response.status_code, 404)
        self.course_request.refresh_from_db()
        self.assertEqual(self.course_request.status, CourseRequest.STATUS_PENDING)

    def test_public_role_signup_is_disabled_by_default(self):
        response = self.client.get(reverse("counselor_signup"))
        self.assertEqual(response.status_code, 403)
