from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from Pathway.access import (
    _get_parent_linked_students,
    parent_required,
    record_or_404,
    student_required,
)
from Pathway.http import TTS_VOICES, chat_payload
from Pathway.services.ai_advisor import (
    generate_ai_advisor_reply,
)
from Pathway.services.gemini import generate_tts_audio
from Pathway.services.parent_ai_advisor import generate_parent_ai_reply
from Pathway.services.snapshot import build_student_academic_snapshot


@student_required
def ai_chatbot(request):
    student = request.student
    if not student.district:
        return redirect("select_district")
    snapshot = build_student_academic_snapshot(student)
    return render(
        request,
        "dashboard/ai_chatbot.html",
        {
            "student": student,
            "snapshot": snapshot,
            "ai_enabled": settings.AI_ENABLED,
        },
    )


@student_required
def ai_chatbot_message(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)

    student = request.student
    if not student.district:
        return JsonResponse({"error": "District selection required first."}, status=400)

    try:
        user_message = chat_payload(request)["message"]
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    # Start fresh rather than resend legacy replies containing embedded status notices.
    history_key = f"ai_chat_history_v2_{student.id}"
    history = request.session.get(history_key, [])
    result = generate_ai_advisor_reply(student, user_message, history)
    reply, snapshot = result.text, result.snapshot

    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": reply})
    request.session[history_key] = history[-10:]

    return JsonResponse(
        {
            "response": reply,
            "api_failed": result.api_failed,
            "top_recommendations": snapshot.get("recommended_courses", [])[:3],
            "requirement_gaps": [
                item
                for item in snapshot.get("graduation_requirements", [])
                if item["remaining_credits"] > 0
            ][:5],
        }
    )


@parent_required
def parent_ai_chatbot(request, student_id=None):
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

    snapshot = (
        build_student_academic_snapshot(selected_student)
        if selected_student and selected_student.district
        else None
    )

    return render(
        request,
        "parent/ai_chatbot.html",
        {
            "parent": parent,
            "students": students,
            "selected_student": selected_student,
            "snapshot": snapshot,
            "tts_voice_options": TTS_VOICES,
            "ai_enabled": settings.AI_ENABLED,
        },
    )


@parent_required
def parent_ai_chatbot_message(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)

    parent = request.parent_profile
    try:
        body = chat_payload(request, parent=True)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    message_text = body["message"]
    student_id = body["student_id"]
    enable_tts = body["enable_tts"]
    voice_name = body["voice_name"]

    linked_students = _get_parent_linked_students(parent)
    student = get_object_or_404(linked_students, id=student_id)
    if not student.district:
        return JsonResponse(
            {"error": "This student must select a district before using the advisor."},
            status=400,
        )

    history_key = f"parent_ai_chat_history_v2_{parent.id}_{student.id}"
    history = request.session.get(history_key, [])
    result = generate_parent_ai_reply(parent, student, message_text, history)
    reply, snapshot = result.text, result.snapshot

    history.append({"role": "user", "content": message_text})
    history.append({"role": "assistant", "content": reply})
    request.session[history_key] = history[-12:]

    payload = {
        "response": reply,
        "api_failed": result.api_failed,
        "student_name": f"{student.firstName} {student.lastName}",
        "status": snapshot.get("graduation_status", {}).get("status", "Unknown"),
        "completion_percent": snapshot.get("graduation_status", {}).get("completion_percent", 0),
    }

    if enable_tts:
        try:
            tts_payload = generate_tts_audio(
                reply,
                voice_name=voice_name,
            )
            payload.update(tts_payload)
        except (ValueError, OSError):
            payload["tts_error"] = "Audio is temporarily unavailable. Your text response is ready."

    return JsonResponse(payload)
