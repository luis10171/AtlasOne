from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    firstName = models.CharField(max_length=50)
    lastName = models.CharField(max_length=50)
    gradeLevel = models.IntegerField(
        choices=[(9, "9th Grade"), (10, "10th Grade"), (11, "11th Grade"), (12, "12th Grade")]
    )
    graduationYear = models.IntegerField()
    GPA = models.FloatField()
    district = models.ForeignKey("District", on_delete=models.SET_NULL, null=True)
    assignedCounselor = models.ForeignKey(
        "GuidanceCounselor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_students",
    )

    def __str__(self):
        return f"Name: {self.firstName} {self.lastName}  User: {self.user.username}"


class Subject(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class Course(models.Model):
    name = models.CharField(max_length=200)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    creditValue = models.FloatField()
    prerequisites = models.ManyToManyField("self", blank=True, symmetrical=False)
    instructor = models.CharField(max_length=200)
    isCoreClass = models.BooleanField(
        help_text="Set by district course setup to mark classes required for graduation.",
    )

    def __str__(self):
        return self.name


class Transcript(models.Model):
    student = models.OneToOneField(Student, on_delete=models.CASCADE, related_name="transcript")

    def __str__(self):
        return f"{self.student.firstName} {self.student.lastName}'s Transcript"


class TranscriptEntry(models.Model):
    transcript = models.ForeignKey(Transcript, on_delete=models.CASCADE, related_name="entries")
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    grade = models.IntegerField(help_text="Final numeric grade (0–100)")
    creditsEarned = models.FloatField()
    gradeTaken = models.IntegerField(
        choices=[(9, "9th Grade"), (10, "10th Grade"), (11, "11th Grade"), (12, "12th Grade")]
    )

    def __str__(self):
        return f"{self.course.name}: {self.grade}"


class District(models.Model):
    name = models.CharField(max_length=50)
    state = models.CharField(max_length=50)
    courses = models.ManyToManyField(Course, symmetrical=False, blank=True)

    def __str__(self):
        return self.name


class GraduationRequirement(models.Model):
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name="requirements")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT)
    requiredCredits = models.FloatField()

    def __str__(self):
        return f"{self.subject.name}: {self.requiredCredits} credits"


class TranscriptUpload(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    pdf = models.FileField(upload_to="transcripts")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Transcript upload for {self.student.firstName} {self.student}"


class GuidanceCounselor(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    firstName = models.CharField(max_length=50)
    lastName = models.CharField(max_length=50)
    district = models.ForeignKey("District", on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"Counselor {self.firstName} {self.lastName} ({self.user.username})"


class CourseRequest(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_DENIED = "denied"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_DENIED, "Denied"),
    ]

    GRADE_CHOICES = [
        (9, "9th Grade"),
        (10, "10th Grade"),
        (11, "11th Grade"),
        (12, "12th Grade"),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="course_requests")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="course_requests")
    requested_for_grade = models.IntegerField(choices=GRADE_CHOICES)
    student_note = models.TextField(blank=True)
    counselor_note = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reviewed_by = models.ForeignKey(
        "GuidanceCounselor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_course_requests",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "course", "requested_for_grade"],
                name="unique_student_course_request_per_grade",
            )
        ]

    def __str__(self):
        return (
            f"{self.student.firstName} {self.student.lastName}: "
            f"{self.course.name} ({self.get_status_display()})"
        )


class Parent(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    firstName = models.CharField(max_length=50)
    lastName = models.CharField(max_length=50)
    preferredLanguage = models.CharField(max_length=40, blank=True)
    students = models.ManyToManyField(
        Student,
        through="ParentStudentLink",
        related_name="parents",
    )

    def __str__(self):
        return f"Parent {self.firstName} {self.lastName} ({self.user.username})"


class ParentStudentLink(models.Model):
    RELATION_CHOICES = [
        ("mother", "Mother"),
        ("father", "Father"),
        ("guardian", "Guardian"),
        ("other", "Other"),
    ]

    parent = models.ForeignKey(
        Parent,
        on_delete=models.CASCADE,
        related_name="student_links",
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="parent_links",
    )
    relationship = models.CharField(
        max_length=20,
        choices=RELATION_CHOICES,
        default="guardian",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "student"],
                name="unique_parent_student_link",
            )
        ]

    def __str__(self):
        return (
            f"{self.parent.firstName} {self.parent.lastName} - "
            f"{self.student.firstName} {self.student.lastName}"
        )


class CounselorConversation(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="counselor_conversations",
    )
    counselor = models.ForeignKey(
        GuidanceCounselor,
        on_delete=models.CASCADE,
        related_name="student_conversations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "counselor"],
                name="unique_counselor_student_conversation",
            )
        ]

    def __str__(self):
        return (
            f"Conversation: {self.student.firstName} {self.student.lastName} "
            f"and {self.counselor.firstName} {self.counselor.lastName}"
        )


class CounselorMessage(models.Model):
    conversation = models.ForeignKey(
        CounselorConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="counselor_messages_sent",
    )
    body = models.TextField(max_length=3000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def clean(self):
        participant_ids = {
            self.conversation.student.user_id,
            self.conversation.counselor.user_id,
        }
        if self.sender_id not in participant_ids:
            raise ValidationError("Sender must be part of this conversation.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        CounselorConversation.objects.filter(pk=self.conversation_id).update(
            updated_at=timezone.now()
        )

    def __str__(self):
        return f"{self.sender.username}: {self.body[:40]}"


class ParentCounselorConversation(models.Model):
    parent = models.ForeignKey(
        Parent,
        on_delete=models.CASCADE,
        related_name="counselor_conversations",
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="parent_counselor_conversations",
    )
    counselor = models.ForeignKey(
        GuidanceCounselor,
        on_delete=models.CASCADE,
        related_name="parent_conversations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "student", "counselor"],
                name="unique_parent_student_counselor_conversation",
            )
        ]

    def clean(self):
        if not ParentStudentLink.objects.filter(
            parent=self.parent,
            student=self.student,
        ).exists():
            raise ValidationError("Parent must be linked to the selected student.")
        if (
            self.student.assignedCounselor_id
            and self.student.assignedCounselor_id != self.counselor_id
        ):
            raise ValidationError("Conversation counselor must match the student's counselor.")

    def __str__(self):
        return (
            f"Parent/Counselor Conversation: {self.parent.firstName} "
            f"- {self.student.firstName} - {self.counselor.firstName}"
        )


class ParentCounselorMessage(models.Model):
    conversation = models.ForeignKey(
        ParentCounselorConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="parent_counselor_messages_sent",
    )
    body = models.TextField(max_length=3000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def clean(self):
        participant_ids = {
            self.conversation.parent.user_id,
            self.conversation.counselor.user_id,
        }
        if self.sender_id not in participant_ids:
            raise ValidationError("Sender must be part of this parent-counselor conversation.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        ParentCounselorConversation.objects.filter(pk=self.conversation_id).update(
            updated_at=timezone.now()
        )

    def __str__(self):
        return f"{self.sender.username}: {self.body[:40]}"
