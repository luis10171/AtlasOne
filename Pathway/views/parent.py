from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from Pathway.access import (
    _get_parent_linked_students,
    _resolve_student_counselor,
    parent_required,
    record_or_404,
)
from Pathway.forms import (
    ParentCounselorMessageForm,
)
from Pathway.models import (
    CourseRequest,
    ParentCounselorConversation,
    ParentCounselorMessage,
    Transcript,
    TranscriptEntry,
)
from Pathway.services.graduation import GraduationEngine


@parent_required
def parent_dashboard(request):
    parent = request.parent_profile
    students = _get_parent_linked_students(parent)
    selected_student = None
    selected_student_id = request.GET.get("student", "").strip()

    if students.exists():
        if selected_student_id:
            selected_student = record_or_404(students, selected_student_id)
        else:
            selected_student = students.first()
        if selected_student:
            _resolve_student_counselor(selected_student)

    transcript_entries = TranscriptEntry.objects.none()
    course_requests = CourseRequest.objects.none()
    graduation_status = None
    if selected_student:
        transcript, _ = Transcript.objects.get_or_create(student=selected_student)
        transcript_entries = transcript.entries.select_related("course__subject").order_by(
            "-gradeTaken",
            "course__name",
        )
        course_requests = CourseRequest.objects.filter(student=selected_student).select_related(
            "course__subject",
            "reviewed_by__user",
        )
        if selected_student.district:
            graduation_status = GraduationEngine(selected_student).build_progress_report()

    return render(
        request,
        "parent/dashboard.html",
        {
            "parent": parent,
            "students": students,
            "selected_student": selected_student,
            "transcript_entries": transcript_entries,
            "course_requests": course_requests,
            "graduation_status": graduation_status,
        },
    )


@parent_required
def parent_messages(request, student_id=None):
    parent = request.parent_profile
    students = _get_parent_linked_students(parent)
    selected_student = None

    if student_id is not None:
        selected_student = get_object_or_404(students, id=student_id)
    else:
        selected_student_id = request.GET.get("student", "").strip()
        if selected_student_id:
            selected_student = record_or_404(students, selected_student_id)
        elif students.exists():
            selected_student = students.first()

    conversation = None
    counselor = None
    if selected_student:
        counselor = _resolve_student_counselor(selected_student)
        if counselor:
            conversation, _ = ParentCounselorConversation.objects.get_or_create(
                parent=parent,
                student=selected_student,
                counselor=counselor,
            )
        else:
            messages.error(
                request,
                "No counselor is assigned to this student yet. Ask school staff to assign one.",
            )

    if request.method == "POST" and conversation:
        form = ParentCounselorMessageForm(
            request.POST,
            sender=request.user,
            conversation=conversation,
        )
        if form.is_valid():
            outgoing = form.save(commit=False)
            outgoing.sender = request.user
            outgoing.conversation = conversation
            outgoing.save()
            return redirect("parent_messages_with_student", student_id=selected_student.id)
    else:
        form = ParentCounselorMessageForm(
            sender=request.user,
            conversation=conversation,
        )

    conversation_messages = (
        conversation.messages.select_related("sender")
        if conversation
        else ParentCounselorMessage.objects.none()
    )

    return render(
        request,
        "parent/messages.html",
        {
            "parent": parent,
            "students": students,
            "selected_student": selected_student,
            "assigned_counselor": counselor,
            "conversation": conversation,
            "conversation_messages": conversation_messages,
            "form": form,
        },
    )
