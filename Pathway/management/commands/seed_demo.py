"""Create fictional records in an empty local database for a reproducible demo."""

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from Pathway.models import (
    CounselorConversation,
    CounselorMessage,
    Course,
    CourseRequest,
    District,
    GraduationRequirement,
    GuidanceCounselor,
    Parent,
    ParentStudentLink,
    Student,
    Subject,
    Transcript,
    TranscriptEntry,
)

DEMO_PASSWORD = "AtlasDemo!2026"
DEMO_USERNAMES = ("demo.student", "demo.counselor", "demo.parent")
DEMO_DISTRICT = "Atlas Demo District"


class Command(BaseCommand):
    help = "Create fictional demo accounts. Requires DEBUG and an empty database; safe to rerun."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo accounts can only be created with DJANGO_DEBUG=True.")
        if User.objects.exists() or District.objects.exists():
            if (
                set(User.objects.values_list("username", flat=True)) == set(DEMO_USERNAMES)
                and District.objects.filter(name=DEMO_DISTRICT).count() == 1
                and District.objects.count() == 1
            ):
                self.stdout.write(
                    "Demo accounts already exist. Existing records and passwords were preserved."
                )
                return
            raise CommandError(
                "Use an empty demo database. Existing accounts and districts were not modified."
            )

        district = District.objects.create(name=DEMO_DISTRICT, state="Demo")
        subjects = {
            name: Subject.objects.create(name=name)
            for name in ("Math", "English", "Science", "History")
        }
        catalog = [
            ("Algebra I", "Math", None),
            ("Geometry", "Math", "Algebra I"),
            ("Algebra II", "Math", "Geometry"),
            ("English I", "English", None),
            ("English II", "English", "English I"),
            ("English III", "English", "English II"),
            ("Biology", "Science", None),
            ("Chemistry", "Science", "Biology"),
            ("World History", "History", None),
            ("US History", "History", None),
        ]
        courses = {}
        for name, subject, prerequisite in catalog:
            course = Course.objects.create(
                name=name,
                subject=subjects[subject],
                creditValue=1.0,
                instructor="Demo faculty",
                isCoreClass=True,
            )
            district.courses.add(course)
            if prerequisite:
                course.prerequisites.add(courses[prerequisite])
            courses[name] = course
        for subject, required in (("Math", 3), ("English", 3), ("Science", 2), ("History", 2)):
            GraduationRequirement.objects.create(
                district=district,
                subject=subjects[subject],
                requiredCredits=required,
            )

        users = {
            name: User.objects.create_user(
                username=name,
                password=DEMO_PASSWORD,
                email=f"{name}@example.invalid",
            )
            for name in DEMO_USERNAMES
        }
        counselor = GuidanceCounselor.objects.create(
            user=users["demo.counselor"],
            firstName="Morgan",
            lastName="Reed",
            district=district,
        )
        student = Student.objects.create(
            user=users["demo.student"],
            firstName="Avery",
            lastName="Chen",
            gradeLevel=10,
            graduationYear=timezone.now().year + 2,
            GPA=3.4,
            district=district,
            assignedCounselor=counselor,
        )
        transcript = Transcript.objects.create(student=student)
        for name, grade, year in (
            ("Algebra I", 88, 9),
            ("English I", 91, 9),
            ("Biology", 82, 9),
            ("World History", 79, 9),
            ("Geometry", 0, 10),
            ("English II", 0, 10),
        ):
            TranscriptEntry.objects.create(
                transcript=transcript,
                course=courses[name],
                grade=grade,
                creditsEarned=1.0 if grade else 0.0,
                gradeTaken=year,
            )
        parent = Parent.objects.create(
            user=users["demo.parent"],
            firstName="Jordan",
            lastName="Chen",
        )
        ParentStudentLink.objects.create(parent=parent, student=student, relationship="guardian")
        CourseRequest.objects.create(
            student=student,
            course=courses["Algebra II"],
            requested_for_grade=11,
            student_note="I would like to continue math after completing Geometry this year.",
        )
        conversation = CounselorConversation.objects.create(student=student, counselor=counselor)
        CounselorMessage.objects.create(
            conversation=conversation,
            sender=student.user,
            body="Can we review my science options for next year?",
        )
        self.stdout.write(self.style.SUCCESS("Fictional demo ready."))
        self.stdout.write(f"Accounts: {', '.join(DEMO_USERNAMES)}")
        self.stdout.write(f"Local demo password: {DEMO_PASSWORD}")
