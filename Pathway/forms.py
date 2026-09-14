from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from .models import (
    CounselorMessage,
    Course,
    CourseRequest,
    ParentCounselorMessage,
    Student,
    Transcript,
    TranscriptEntry,
)
from .services.planner import build_next_year_planner, get_missing_prerequisite_names


class StudentSignupForm(UserCreationForm):
    email = forms.EmailField()
    firstName = forms.CharField(label="First name", max_length=50)
    lastName = forms.CharField(label="Last name", max_length=50)
    gradeLevel = forms.TypedChoiceField(
        label="Grade",
        choices=Student._meta.get_field("gradeLevel").choices,
        coerce=int,
    )
    graduationYear = forms.IntegerField(label="Graduation year")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("firstName", "lastName", "email", "username", "gradeLevel", "graduationYear")

    def clean_graduationYear(self):
        year = self.cleaned_data["graduationYear"]
        current_year = timezone.now().year
        if not current_year <= year <= current_year + 6:
            raise forms.ValidationError(
                f"Graduation year must be between {current_year} and {current_year + 6}."
            )
        return year

    @transaction.atomic
    def save(self, commit=True):
        if not commit:
            raise ValueError("Student signup must save the user and profile together.")
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["firstName"]
        user.last_name = self.cleaned_data["lastName"]
        user.save()
        student = Student.objects.create(
            user=user,
            firstName=user.first_name,
            lastName=user.last_name,
            gradeLevel=self.cleaned_data["gradeLevel"],
            graduationYear=self.cleaned_data["graduationYear"],
            GPA=0.0,
        )
        Transcript.objects.create(student=student)
        return user


class StudentDistrictForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ["district"]
        widgets = {
            "district": forms.Select(attrs={"class": "form-control"}),
        }


class TranscriptEntryForm(forms.ModelForm):
    class Meta:
        model = TranscriptEntry
        fields = ["course", "grade", "creditsEarned", "gradeTaken"]

    def __init__(self, *args, student=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.student = student
        self.fields["creditsEarned"].widget.attrs.update({"min": 0, "step": 0.5})
        if self.student and self.student.district:
            self.fields["course"].queryset = self.student.district.courses.order_by("name")
        elif self.student:
            self.fields["course"].queryset = Course.objects.none()

    def clean_grade(self):
        grade = self.cleaned_data.get("grade")
        if grade is None:
            raise forms.ValidationError("Grade is required.")
        grade = int(grade)
        if grade < 0 or grade > 100:
            raise forms.ValidationError("Grade must be between 0 and 100.")
        return grade

    def clean_creditsEarned(self):
        credits = self.cleaned_data.get("creditsEarned")
        course = self.cleaned_data.get("course")
        if not course:
            raise forms.ValidationError("Course is missing.")
        if credits is None:
            raise forms.ValidationError("Credits earned is required.")
        creditCheck = course.creditValue
        if credits < 0 or credits > creditCheck:
            raise forms.ValidationError(f"Credit amount must be between 0.0 and {creditCheck}.")

        return credits

    def clean_gradeTaken(self):
        gradeTaken = self.cleaned_data["gradeTaken"]

        if not self.student:
            raise forms.ValidationError("Student context is missing.")

        if gradeTaken > self.student.gradeLevel:
            raise forms.ValidationError("You cannot add courses above your current grade level.")

        return gradeTaken


class CourseRequestForm(forms.ModelForm):
    class Meta:
        model = CourseRequest
        fields = ["course", "student_note"]
        widgets = {
            "student_note": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Optional note for your counselor.",
                }
            )
        }

    def __init__(self, *args, student=None, target_grade=None, planner=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.student = student
        self.target_grade = target_grade
        self.fields["course"].queryset = Course.objects.none()

        if not self.student or not self.student.district:
            return

        planner = planner if planner is not None else build_next_year_planner(self.student)
        eligible_ids = [item["course"].id for item in planner["eligible_courses"]]
        already_requested_ids = set(
            CourseRequest.objects.filter(
                student=self.student,
                requested_for_grade=self.target_grade,
            ).values_list("course_id", flat=True)
        )
        self.fields["course"].queryset = (
            self.student.district.courses.filter(id__in=eligible_ids)
            .exclude(id__in=already_requested_ids)
            .order_by("subject__name", "name")
        )

    def clean(self):
        cleaned_data = super().clean()
        if not self.student:
            raise forms.ValidationError("Student context is required.")
        if int(self.student.gradeLevel) >= 12:
            raise forms.ValidationError("12th grade students cannot submit next-year requests.")
        if not self.student.district:
            raise forms.ValidationError("You must select a district first.")
        return cleaned_data

    def clean_course(self):
        course = self.cleaned_data.get("course")
        if not course:
            return course

        if not self.student:
            raise forms.ValidationError("Student context is required.")
        if not self.student.district:
            raise forms.ValidationError("You must select a district first.")
        if not self.student.district.courses.filter(id=course.id).exists():
            raise forms.ValidationError("Selected course is not in your district.")

        missing_prereqs = get_missing_prerequisite_names(self.student, course)
        if missing_prereqs:
            raise forms.ValidationError(
                f"You still need these prerequisites: {', '.join(missing_prereqs)}."
            )
        return course


class ConversationMessageForm(forms.ModelForm):
    """Bind participant context before ModelForm invokes model validation."""

    participant_relation = "student"

    class Meta:
        fields = ["body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 3, "placeholder": "Type your message..."})}

    def __init__(self, *args, sender=None, conversation=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.sender = sender
        self.conversation = conversation
        if sender:
            self.instance.sender = sender
        if conversation:
            self.instance.conversation = conversation

    def clean_body(self):
        body = self.cleaned_data.get("body", "").strip()
        if not body:
            raise forms.ValidationError("Message cannot be empty.")
        return body

    def clean(self):
        cleaned_data = super().clean()
        if not self.sender or not self.conversation:
            raise forms.ValidationError("Conversation context is required.")
        participant = getattr(self.conversation, self.participant_relation)
        if self.sender.id not in {participant.user_id, self.conversation.counselor.user_id}:
            raise forms.ValidationError("You are not part of this conversation.")
        return cleaned_data


class CounselorMessageForm(ConversationMessageForm):
    class Meta(ConversationMessageForm.Meta):
        model = CounselorMessage


class ParentCounselorMessageForm(ConversationMessageForm):
    participant_relation = "parent"

    class Meta(ConversationMessageForm.Meta):
        model = ParentCounselorMessage
