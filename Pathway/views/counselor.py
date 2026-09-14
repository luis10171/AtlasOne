from django.contrib import messages
from django.db import transaction
from django.forms import modelformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from pdfminer.pdfexceptions import PDFException

from Pathway.access import (
    _get_counselor_students,
    counselor_conversations,
    counselor_required,
    record_or_404,
)
from Pathway.access import (
    parent_conversations as accessible_parent_conversations,
)
from Pathway.forms import (
    CounselorMessageForm,
    ParentCounselorMessageForm,
    TranscriptEntryForm,
)
from Pathway.models import (
    CounselorConversation,
    CounselorMessage,
    CourseRequest,
    ParentCounselorMessage,
    Transcript,
    TranscriptEntry,
)
from Pathway.services.graduation import GraduationEngine
from Pathway.utils.pdf_parser import MAX_TRANSCRIPT_ROWS, extract_courses_from_pdf


@counselor_required
def add_course(request, student_id):
    counselor = request.counselor
    student = get_object_or_404(
        _get_counselor_students(counselor),
        id=student_id,
    )
    if not student.district:
        messages.error(request, "Select your district before adding transcript courses.")
        return redirect("counselor_student_profile", student_id=student.id)

    transcript, _ = Transcript.objects.get_or_create(student=student)
    form = TranscriptEntryForm(student=student)
    formset = None
    unmatched_courses = []

    if request.method == "POST" and "upload_pdf" in request.POST:
        uploaded_file = request.FILES.get("transcript_pdf")

        if not uploaded_file:
            messages.error(request, "Please choose a PDF file before uploading.")
        elif uploaded_file.size > 10 * 1024 * 1024:
            messages.error(request, "Transcript PDFs must be 10 MB or smaller.")
        elif not uploaded_file.read(5).startswith(b"%PDF-"):
            messages.error(request, "The uploaded file is not a valid PDF.")
        else:
            try:
                uploaded_file.seek(0)
                parsed_courses = extract_courses_from_pdf(
                    uploaded_file,
                    student,
                    student.district.courses.all(),
                )
            except ValueError as exc:
                messages.error(request, str(exc))
            except (PDFException, OSError):
                messages.error(
                    request,
                    "We could not parse this transcript PDF. Try a clearer export or add courses manually.",
                )
            else:
                if not parsed_courses:
                    messages.warning(
                        request,
                        "No transcript rows were detected. Please verify the PDF format.",
                    )
                else:
                    initial_data = []
                    for entry in parsed_courses:
                        if entry["course_id"] is None:
                            unmatched_courses.append(entry["course_name"])
                            continue
                        initial_data.append(
                            {
                                "course": entry["course_id"],
                                "grade": entry["grade"],
                                "creditsEarned": entry["credits"],
                                "gradeTaken": entry["grade_taken"] or student.gradeLevel,
                            }
                        )

                    if initial_data:
                        DynamicFormSet = modelformset_factory(
                            TranscriptEntry,
                            form=TranscriptEntryForm,
                            extra=len(initial_data),
                            max_num=MAX_TRANSCRIPT_ROWS,
                            absolute_max=MAX_TRANSCRIPT_ROWS,
                            validate_max=True,
                            can_delete=True,
                        )
                        formset = DynamicFormSet(
                            queryset=TranscriptEntry.objects.none(),
                            initial=initial_data,
                            form_kwargs={"student": student},
                        )

                    if unmatched_courses:
                        preview_list = ", ".join(sorted(set(unmatched_courses[:8])))
                        messages.warning(
                            request,
                            f"Some course names did not auto-match district courses: {preview_list}",
                        )
                    if not initial_data:
                        messages.warning(
                            request,
                            "No matched district courses were found in this upload. Unmatched rows were removed.",
                        )

    elif request.method == "POST" and "save_pdf_courses" in request.POST:
        DynamicFormSet = modelformset_factory(
            TranscriptEntry,
            form=TranscriptEntryForm,
            extra=0,
            max_num=MAX_TRANSCRIPT_ROWS,
            absolute_max=MAX_TRANSCRIPT_ROWS,
            validate_max=True,
            can_delete=True,
        )
        formset = DynamicFormSet(
            request.POST,
            queryset=TranscriptEntry.objects.none(),
            form_kwargs={"student": student},
        )

        if formset.is_valid():
            saved_count = 0
            with transaction.atomic():
                for form_instance in formset:
                    if form_instance.cleaned_data and not form_instance.cleaned_data.get("DELETE"):
                        course = form_instance.cleaned_data.get("course")
                        if not course:
                            continue
                        entry = form_instance.save(commit=False)
                        entry.transcript = transcript
                        entry.save()
                        saved_count += 1

            if saved_count > 0:
                messages.success(
                    request,
                    f"{saved_count} transcript entr{'y' if saved_count == 1 else 'ies'} saved successfully!",
                )
            else:
                messages.warning(request, "No new transcript entries were saved.")
            return redirect("counselor_student_profile", student_id=student.id)

        messages.error(request, "Please fix the errors below before saving parsed courses.")
    elif request.method == "POST":
        form = TranscriptEntryForm(request.POST, student=student)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.transcript = transcript
            entry.save()
            messages.success(request, "Transcript entry saved!")
            return redirect("counselor_student_profile", student_id=student.id)

    return render(
        request,
        "dashboard/add_course.html",
        {
            "counselor": counselor,
            "student": student,
            "form": form,
            "formset": formset,
            "unmatched_courses": sorted(set(unmatched_courses)),
        },
    )


@counselor_required
def counselor_dashboard(request):
    counselor = request.counselor
    counselor_students = _get_counselor_students(counselor)
    pending_requests = CourseRequest.objects.filter(
        student__in=counselor_students,
        status=CourseRequest.STATUS_PENDING,
    ).select_related("student__district", "student__user", "course__subject")
    reviewed_requests = (
        CourseRequest.objects.exclude(status=CourseRequest.STATUS_PENDING)
        .filter(student__in=counselor_students)
        .select_related("student__user", "course__subject", "reviewed_by__user")[:15]
    )
    students = counselor_students
    conversations = counselor_conversations(counselor)[:10]
    parent_conversations = accessible_parent_conversations(counselor)

    return render(
        request,
        "counselor/dashboard.html",
        {
            "counselor": counselor,
            "pending_requests": pending_requests,
            "reviewed_requests": reviewed_requests,
            "students": students,
            "conversation_threads": conversations,
            "parent_conversation_threads": parent_conversations[:10],
            "pending_count": pending_requests.count(),
            "approved_count": CourseRequest.objects.filter(
                student__in=counselor_students, status=CourseRequest.STATUS_APPROVED
            ).count(),
            "denied_count": CourseRequest.objects.filter(
                student__in=counselor_students, status=CourseRequest.STATUS_DENIED
            ).count(),
            "parent_thread_count": parent_conversations.count(),
        },
    )


@counselor_required
def review_course_request(request, request_id):
    if request.method != "POST":
        return redirect("counselor_dashboard")

    counselor = request.counselor
    course_request = get_object_or_404(
        CourseRequest.objects.select_related("student"),
        id=request_id,
        student__in=_get_counselor_students(counselor),
    )
    decision = request.POST.get("decision", "").strip().lower()
    counselor_note = request.POST.get("counselor_note", "").strip()

    if decision == "approve":
        course_request.status = CourseRequest.STATUS_APPROVED
        decision_label = "approved"
    elif decision == "deny":
        course_request.status = CourseRequest.STATUS_DENIED
        decision_label = "denied"
    else:
        messages.error(request, "Invalid review decision.")
        return redirect("counselor_dashboard")

    course_request.reviewed_by = counselor
    course_request.counselor_note = counselor_note
    course_request.save(update_fields=["status", "reviewed_by", "counselor_note", "updated_at"])
    messages.success(
        request,
        f"Request for {course_request.student.firstName} {course_request.student.lastName} was {decision_label}.",
    )

    next_page = request.POST.get("next", "").strip()
    if next_page and url_has_allowed_host_and_scheme(
        next_page,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_page)
    return redirect("counselor_dashboard")


@counselor_required
def counselor_student_profile(request, student_id):
    counselor = request.counselor
    student = get_object_or_404(
        _get_counselor_students(counselor),
        id=student_id,
    )
    transcript, _ = Transcript.objects.get_or_create(student=student)
    transcript_entries = transcript.entries.select_related("course__subject").order_by(
        "-gradeTaken",
        "course__name",
    )
    course_requests = CourseRequest.objects.filter(student=student).select_related(
        "course__subject",
        "reviewed_by__user",
    )
    graduation_status = (
        GraduationEngine(student).build_progress_report() if student.district else None
    )
    conversation, _ = CounselorConversation.objects.get_or_create(
        student=student,
        counselor=counselor,
    )
    recent_messages = conversation.messages.select_related("sender").order_by("-created_at")[:6]

    return render(
        request,
        "counselor/student_profile.html",
        {
            "counselor": counselor,
            "student": student,
            "transcript_entries": transcript_entries,
            "course_requests": course_requests,
            "graduation_status": graduation_status,
            "conversation": conversation,
            "recent_messages": recent_messages,
        },
    )


@counselor_required
def counselor_messages(request, student_id=None):
    counselor = request.counselor
    selected_conversation = None

    if student_id is not None:
        student = get_object_or_404(_get_counselor_students(counselor), id=student_id)
        selected_conversation, _ = CounselorConversation.objects.get_or_create(
            counselor=counselor,
            student=student,
        )

    if request.method == "POST":
        conversation_id = request.POST.get("conversation_id", "").strip()
        if conversation_id:
            selected_conversation = record_or_404(
                counselor_conversations(counselor), conversation_id
            )

    conversations = counselor_conversations(counselor)

    if not selected_conversation and conversations.exists():
        selected_conversation = conversations.first()

    if request.method == "POST" and selected_conversation:
        form = CounselorMessageForm(
            request.POST,
            sender=request.user,
            conversation=selected_conversation,
        )
        if form.is_valid():
            outgoing = form.save(commit=False)
            outgoing.sender = request.user
            outgoing.conversation = selected_conversation
            outgoing.save()
            return redirect(
                "counselor_messages_with_student",
                student_id=selected_conversation.student_id,
            )
    else:
        form = CounselorMessageForm(
            sender=request.user,
            conversation=selected_conversation,
        )

    conversation_messages = (
        selected_conversation.messages.select_related("sender")
        if selected_conversation
        else CounselorMessage.objects.none()
    )

    return render(
        request,
        "counselor/messages.html",
        {
            "counselor": counselor,
            "conversations": conversations,
            "selected_conversation": selected_conversation,
            "conversation_messages": conversation_messages,
            "form": form,
        },
    )


@counselor_required
def counselor_parent_messages(request, conversation_id=None):
    counselor = request.counselor
    conversations = accessible_parent_conversations(counselor)

    selected_conversation = None
    if conversation_id is not None:
        selected_conversation = get_object_or_404(
            conversations,
            id=conversation_id,
        )
    elif conversations.exists():
        selected_conversation = conversations.first()

    if request.method == "POST":
        posted_id = request.POST.get("conversation_id", "").strip()
        if posted_id:
            selected_conversation = record_or_404(conversations, posted_id)

    if request.method == "POST" and selected_conversation:
        form = ParentCounselorMessageForm(
            request.POST,
            sender=request.user,
            conversation=selected_conversation,
        )
        if form.is_valid():
            outgoing = form.save(commit=False)
            outgoing.sender = request.user
            outgoing.conversation = selected_conversation
            outgoing.save()
            return redirect(
                "counselor_parent_messages_with_conversation",
                conversation_id=selected_conversation.id,
            )
    else:
        form = ParentCounselorMessageForm(
            sender=request.user,
            conversation=selected_conversation,
        )

    conversation_messages = (
        selected_conversation.messages.select_related("sender")
        if selected_conversation
        else ParentCounselorMessage.objects.none()
    )

    return render(
        request,
        "counselor/parent_messages.html",
        {
            "counselor": counselor,
            "conversations": conversations,
            "selected_conversation": selected_conversation,
            "conversation_messages": conversation_messages,
            "form": form,
        },
    )
