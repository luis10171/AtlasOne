import os
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from Pathway.models import (
    Course,
    District,
    GraduationRequirement,
    GuidanceCounselor,
    Student,
    Subject,
    Transcript,
    TranscriptEntry,
)
from Pathway.services.ai_advisor import (
    build_student_academic_snapshot,
)
from Pathway.services.graduation import GraduationEngine


class CoreCourseRequirementTests(TestCase):
    def setUp(self):
        self.math = Subject.objects.create(name="Math")
        self.ela = Subject.objects.create(name="ELA")
        self.district = District.objects.create(name="Test District", state="CA")

        self.core_course = Course.objects.create(
            name="Algebra I",
            subject=self.math,
            creditValue=1.0,
            instructor="Teacher A",
            isCoreClass=True,
        )
        self.non_core_course = Course.objects.create(
            name="Creative Writing",
            subject=self.ela,
            creditValue=1.0,
            instructor="Teacher B",
            isCoreClass=False,
        )
        self.district.courses.add(self.core_course, self.non_core_course)

        GraduationRequirement.objects.create(
            district=self.district,
            subject=self.math,
            requiredCredits=2.0,
        )

        self.student_user = User.objects.create_user(
            username="student1",
            password="pass12345",
        )
        self.student = Student.objects.create(
            user=self.student_user,
            firstName="Test",
            lastName="Student",
            gradeLevel=10,
            graduationYear=2028,
            GPA=3.2,
            district=self.district,
        )
        self.transcript = Transcript.objects.create(student=self.student)
        self.counselor_user = User.objects.create_user(
            username="test_counselor",
            password="StrongPass1!",
        )
        self.counselor = GuidanceCounselor.objects.create(
            user=self.counselor_user,
            firstName="Test",
            lastName="Counselor",
            district=self.district,
        )

    def test_course_is_core_class_defaults_to_false(self):
        self.assertFalse(self.non_core_course.isCoreClass)

    def test_graduation_alerts_include_missing_core_classes(self):
        engine = GraduationEngine(self.student)

        alerts = engine.generateAlerts()

        self.assertIn("Missing required core class: Algebra I", alerts)

    def test_snapshot_tracks_missing_core_courses_and_prioritizes_them(self):
        snapshot = build_student_academic_snapshot(self.student)

        missing_core_names = {course["name"] for course in snapshot["missing_core_courses"]}
        self.assertIn("Algebra I", missing_core_names)
        self.assertTrue(snapshot["recommended_courses"][0]["is_core_class"])

    def test_missing_core_course_clears_after_completion(self):
        TranscriptEntry.objects.create(
            transcript=self.transcript,
            course=self.core_course,
            grade=92,
            creditsEarned=1.0,
            gradeTaken=9,
        )

        engine = GraduationEngine(self.student)
        alerts = engine.generateAlerts()

        self.assertNotIn("Missing required core class: Algebra I", alerts)

    def test_on_track_when_remaining_plan_is_feasible(self):
        geometry = Course.objects.create(
            name="Geometry",
            subject=self.math,
            creditValue=1.0,
            instructor="Teacher C",
            isCoreClass=False,
        )
        self.district.courses.add(geometry)

        TranscriptEntry.objects.create(
            transcript=self.transcript,
            course=self.core_course,
            grade=90,
            creditsEarned=1.0,
            gradeTaken=9,
        )

        report = GraduationEngine(self.student).build_progress_report()

        self.assertTrue(report["on_track"])
        self.assertEqual(report["status"], "On Track")
        self.assertGreaterEqual(report["course_slots_remaining"], report["minimum_courses_needed"])

    def test_off_track_when_course_load_exceeds_remaining_time(self):
        science = Subject.objects.create(name="Science")
        rushed_district = District.objects.create(name="Rushed District", state="CA")
        GraduationRequirement.objects.create(
            district=rushed_district,
            subject=self.math,
            requiredCredits=4.0,
        )
        GraduationRequirement.objects.create(
            district=rushed_district,
            subject=science,
            requiredCredits=2.0,
        )

        for name, subject in [
            ("Algebra I", self.math),
            ("Geometry", self.math),
            ("Algebra II", self.math),
            ("Pre-Calculus", self.math),
            ("Biology", science),
            ("Chemistry", science),
        ]:
            rushed_district.courses.add(
                Course.objects.create(
                    name=name,
                    subject=subject,
                    creditValue=1.0,
                    instructor="Teacher X",
                    isCoreClass=True,
                )
            )

        user = User.objects.create_user(username="senior1", password="pass12345")
        senior = Student.objects.create(
            user=user,
            firstName="Senior",
            lastName="Student",
            gradeLevel=12,
            graduationYear=2026,
            GPA=2.8,
            district=rushed_district,
        )
        Transcript.objects.create(student=senior)

        report = GraduationEngine(senior).build_progress_report()

        self.assertFalse(report["on_track"])
        self.assertIn("course slots remain", " ".join(report["alerts"]))

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_dashboard_shows_off_track_alert_and_ai_insight(self):
        self.client.login(username="student1", password="pass12345")

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Off Track")
        self.assertContains(response, "Prioritize Algebra I")

    def test_manual_add_course_allows_duplicates(self):
        self.client.login(username="test_counselor", password="StrongPass1!")
        payload = {
            "course": self.non_core_course.id,
            "grade": 95,
            "creditsEarned": "1.0",
            "gradeTaken": 10,
        }

        first = self.client.post(reverse("add_course", args=[self.student.id]), payload)
        second = self.client.post(reverse("add_course", args=[self.student.id]), payload)

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(
            TranscriptEntry.objects.filter(
                transcript=self.transcript,
                course=self.non_core_course,
            ).count(),
            2,
        )

    @mock.patch("Pathway.views.counselor.extract_courses_from_pdf")
    def test_parsed_unmatched_courses_are_removed_from_confirmation_form(self, mock_parser):
        self.client.login(username="test_counselor", password="StrongPass1!")
        mock_parser.return_value = [
            {
                "course_id": self.non_core_course.id,
                "course_name": self.non_core_course.name,
                "grade": 88,
                "credits": 1.0,
                "grade_taken": 10,
            },
            {
                "course_id": None,
                "course_name": "Unknown PE Variant",
                "grade": 90,
                "credits": 1.0,
                "grade_taken": 10,
            },
        ]

        upload = SimpleUploadedFile(
            "transcript.pdf", b"%PDF-1.4 test", content_type="application/pdf"
        )
        response = self.client.post(
            reverse("add_course", args=[self.student.id]),
            {"upload_pdf": "1", "transcript_pdf": upload},
        )

        self.assertEqual(response.status_code, 200)
        formset = response.context["formset"]
        self.assertIsNotNone(formset)
        self.assertEqual(len(formset.forms), 1)
        self.assertContains(response, "did not auto-match district courses")

    def test_student_cannot_access_counselor_add_course_route(self):
        self.client.login(username="student1", password="pass12345")

        response = self.client.get(reverse("add_course", args=[self.student.id]))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("dashboard"))

    def test_in_progress_current_year_course_is_not_treated_as_missing(self):
        TranscriptEntry.objects.create(
            transcript=self.transcript,
            course=self.core_course,
            grade=0,
            creditsEarned=0.0,
            gradeTaken=self.student.gradeLevel,
        )

        report = GraduationEngine(self.student).build_progress_report()
        snapshot = build_student_academic_snapshot(self.student)

        self.assertNotIn("Missing required core class: Algebra I", report["alerts"])
        self.assertEqual(snapshot["in_progress_courses"][0]["name"], "Algebra I")
        self.assertEqual(snapshot["taken_courses"][0]["status"], "in_progress")
