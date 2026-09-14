from django.contrib import messages
from django.db import IntegrityError
from django.shortcuts import redirect, render
from django.urls import reverse

from Pathway.access import (
    counselors_for_student,
    record_or_404,
    student_required,
)
from Pathway.forms import (
    CounselorMessageForm,
    CourseRequestForm,
    StudentDistrictForm,
)
from Pathway.models import (
    CounselorConversation,
    CounselorMessage,
    CourseRequest,
    Student,
    TranscriptEntry,
)
from Pathway.services.ai_advisor import (
    generate_on_track_ai_insight,
)
from Pathway.services.graduation import GraduationEngine
from Pathway.services.planner import build_next_year_planner


@student_required
def select_district(request):
    student = request.student
    if request.method == "POST":
        form = StudentDistrictForm(request.POST, instance=student)
        if form.is_valid():
            if student.pk and student.district_id != Student.objects.get(pk=student.pk).district_id:
                student.assignedCounselor = None
            form.save()
            return redirect("dashboard")
    else:
        form = StudentDistrictForm(instance=student)
    return render(request, "student/select_district.html", {"form": form})


@student_required
def dashboard(request):
    student = request.student
    if not student.district:
        return redirect("select_district")

    transcript_entries = (
        TranscriptEntry.objects.filter(transcript__student=student)
        .select_related("course")
        .order_by("-gradeTaken", "course__name")
    )
    graduation_status = GraduationEngine(student).build_progress_report()
    off_track_ai_insight = None
    if not graduation_status["on_track"]:
        off_track_ai_insight = generate_on_track_ai_insight(student, graduation_status)

    return render(
        request,
        "dashboard/dashboard.html",
        {
            "student": student,
            "transcript_entries": transcript_entries,
            "graduation_status": graduation_status,
            "off_track_ai_insight": off_track_ai_insight,
        },
    )


@student_required
def next_year_planner(request):
    student = request.student
    if not student.district:
        messages.error(request, "Select your district before opening the planner.")
        return redirect("select_district")
    if int(student.gradeLevel) >= 12:
        messages.error(
            request,
            "Next-year planner is only available for students who are not in 12th grade.",
        )
        return redirect("dashboard")

    planner = build_next_year_planner(student)
    target_grade = planner["target_grade"]
    existing_requests = CourseRequest.objects.filter(
        student=student,
        requested_for_grade=target_grade,
    ).select_related("course__subject", "reviewed_by__user")

    if request.method == "POST":
        form = CourseRequestForm(
            request.POST,
            student=student,
            target_grade=target_grade,
            planner=planner,
        )
        if form.is_valid():
            course_request = form.save(commit=False)
            course_request.student = student
            course_request.requested_for_grade = target_grade
            try:
                course_request.save()
            except IntegrityError:
                messages.error(
                    request,
                    "That course request already exists for your next-year plan.",
                )
            else:
                messages.success(
                    request,
                    "Course request submitted to guidance counselors for review.",
                )
            return redirect("next_year_planner")
    else:
        form = CourseRequestForm(student=student, target_grade=target_grade, planner=planner)

    return render(
        request,
        "dashboard/next_year_planner.html",
        {
            "student": student,
            "target_grade": target_grade,
            "form": form,
            "eligible_courses": planner["eligible_courses"],
            "blocked_courses": planner["blocked_courses"],
            "existing_requests": existing_requests,
        },
    )


@student_required
def student_messages(request):
    student = request.student
    counselors = counselors_for_student(student)
    selected_counselor = None
    conversation = None

    selected_counselor_id = request.GET.get("counselor", "").strip()
    if request.method == "POST":
        selected_counselor_id = request.POST.get("counselor_id", "").strip()

    if counselors.exists():
        if selected_counselor_id:
            selected_counselor = record_or_404(counselors, selected_counselor_id)
        else:
            selected_counselor = counselors.first()
        conversation, _ = CounselorConversation.objects.get_or_create(
            student=student,
            counselor=selected_counselor,
        )

    if request.method == "POST":
        if not conversation:
            messages.error(request, "No guidance counselor is available to message.")
            return redirect("student_messages")
        form = CounselorMessageForm(
            request.POST,
            sender=request.user,
            conversation=conversation,
        )
        if form.is_valid():
            outgoing = form.save(commit=False)
            outgoing.sender = request.user
            outgoing.conversation = conversation
            outgoing.save()
            return redirect(f"{reverse('student_messages')}?counselor={selected_counselor.id}")
    else:
        form = CounselorMessageForm(
            sender=request.user,
            conversation=conversation,
        )

    conversation_messages = (
        conversation.messages.select_related("sender")
        if conversation
        else CounselorMessage.objects.none()
    )

    return render(
        request,
        "dashboard/student_messages.html",
        {
            "student": student,
            "counselors": counselors,
            "selected_counselor": selected_counselor,
            "conversation": conversation,
            "conversation_messages": conversation_messages,
            "form": form,
        },
    )
