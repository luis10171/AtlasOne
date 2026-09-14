import json
import logging
import os
import re
from urllib import error

from django.conf import settings

from Pathway.services.advisor_reply import AdvisorReply
from Pathway.services.gemini import DEFAULT_GEMINI_TEXT_MODEL, call_gemini_text
from Pathway.services.snapshot import build_student_academic_snapshot

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are AtlasOne AI, a high school academic advisor assistant.
Your job is to guide one student using only the provided district and transcript data.

Rules:
1) Give practical, student-safe guidance with clear next steps.
2) Use plain, short language by default.
3) If the user asks about a specific class: discuss fit, prerequisites, and why it helps their goals.
4) If the user asks for parent-friendly help or translation: explain U.S. school terms simply and provide a translated version in the requested language.
5) Never invent courses, credits, or district requirements. If information is missing, say so.
6) Include a short disclaimer that final scheduling decisions should be confirmed with a school counselor.
7) Treat transcript rows with grade 0 and credits 0.0 in the student's current grade level as in-progress courses, not failed courses.
""".strip()
FALLBACK_LANGUAGE_KEYWORDS = {
    "es": ["spanish", "espanol", "espanol", "castellano", "en espanol", "in spanish"],
    "fr": ["french", "francais", "en francais", "in french"],
    "pt": ["portuguese", "portugues", "em portugues", "in portuguese"],
}
FALLBACK_TRANSLATION_LINES = {
    "en": [
        "Parent-friendly summary:",
        "Credits are units students earn by passing classes.",
        "Graduation requires enough credits across required subjects.",
        "Please confirm final scheduling decisions with your counselor.",
    ],
    "es": [
        "Resumen para familias:",
        "Los creditos son unidades que se ganan al aprobar clases.",
        "Para graduarse se necesitan suficientes creditos en materias requeridas.",
        "Confirma las decisiones finales de horario con tu consejero escolar.",
    ],
    "fr": [
        "Resume pour les familles:",
        "Les credits sont des unites gagnees en reussissant les cours.",
        "Le diplome exige assez de credits dans les matieres requises.",
        "Confirmez les decisions finales avec votre conseiller scolaire.",
    ],
    "pt": [
        "Resumo para familias:",
        "Creditos sao unidades obtidas ao passar nas aulas.",
        "A graduacao exige creditos suficientes nas materias obrigatorias.",
        "Confirme as decisoes finais de horario com seu orientador escolar.",
    ],
}
TRANSLATION_REQUEST_TERMS = [
    "translate",
    "translation",
    "parent",
    "parents",
    "family",
    "spanish",
    "espanol",
    "french",
    "francais",
    "portuguese",
    "portugues",
]


def _detect_fallback_language(user_message):
    lowered = str(user_message or "").lower()
    for language_code, keywords in FALLBACK_LANGUAGE_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return language_code
    if re.search(r"[\u0600-\u06FF]", str(user_message or "")):
        return "en"
    return "en"


def _is_translation_related_message(user_message):
    lowered = str(user_message or "").lower()
    if any(term in lowered for term in TRANSLATION_REQUEST_TERMS):
        return True
    return bool(re.search(r"[\u0600-\u06FF]", str(user_message or "")))


def _build_localized_translation_fallback(user_message):
    language_code = _detect_fallback_language(user_message)
    lines = FALLBACK_TRANSLATION_LINES.get(
        language_code,
        FALLBACK_TRANSLATION_LINES["en"],
    )
    return " ".join(lines)


def _rule_based_fallback(snapshot, user_message):
    lowered = user_message.lower()
    recommendations = snapshot.get("recommended_courses", [])
    requirements = snapshot.get("graduation_requirements", [])
    gaps = [item for item in requirements if item["remaining_credits"] > 0]
    course_match = next(
        (
            course
            for course in snapshot.get("eligible_courses", []) + snapshot.get("blocked_courses", [])
            if course["name"].lower() in lowered
        ),
        None,
    )

    if course_match:
        prereq_text = (
            ", ".join(course_match["prerequisites"]) if course_match["prerequisites"] else "none"
        )
        core_note = (
            " This class is currently marked as a district core requirement."
            if course_match.get("is_core_class")
            else ""
        )
        if course_match["missing_prerequisites"]:
            missing = ", ".join(course_match["missing_prerequisites"])
            return (
                f"{course_match['name']} can be a good fit for {course_match['subject']}. "
                f"Prerequisites: {prereq_text}. You still need: {missing}. "
                f"Finish those courses first, then consider this class with your counselor.{core_note}"
            )
        if course_match.get("in_progress_prerequisites"):
            pending = ", ".join(course_match["in_progress_prerequisites"])
            return (
                f"{course_match['name']} depends on passing {pending}, which is still in progress. "
                "You can request it for next year conditionally; confirm eligibility with your counselor."
            )
        return (
            f"{course_match['name']} is currently available for you. "
            f"Subject: {course_match['subject']}. Prerequisites: {prereq_text}. "
            f"It is a reasonable next option based on your completed transcript.{core_note}"
        )

    if _is_translation_related_message(user_message):
        return _build_localized_translation_fallback(user_message)

    lines = ["Based on your transcript and district requirements, here are strong next steps:"]
    for item in recommendations[:3]:
        lines.append(f"- {item['name']} ({item['subject']}): {', '.join(item['why'])}.")
    if gaps:
        urgent = ", ".join(
            f"{item['subject']} ({item['remaining_credits']} credits left)" for item in gaps[:3]
        )
        lines.append(f"Priority gaps to close: {urgent}.")
    core_gaps = snapshot.get("missing_core_courses", [])
    if core_gaps:
        core_text = ", ".join(course["name"] for course in core_gaps[:3])
        lines.append(f"Required core classes still pending: {core_text}.")
    in_progress = snapshot.get("in_progress_courses", [])
    if in_progress:
        in_progress_text = ", ".join(course["name"] for course in in_progress[:3])
        lines.append(
            f"Currently in progress (grade 0 and 0.0 credits this year): {in_progress_text}."
        )
    grad_status = snapshot.get("graduation_status") or {}
    if not grad_status.get("on_track", True):
        lines.append("You are currently off track for on-time graduation.")
        for action in grad_status.get("recommended_actions", [])[:3]:
            lines.append(f"- {action}")
    lines.append("Confirm final class selection with your counselor.")
    return "\n".join(lines)


def _rule_based_on_track_insight(progress_report):
    if progress_report.get("on_track"):
        return "You are on track for graduation. Keep following your district plan and confirm next-semester choices with your counselor."

    lines = [
        "You are currently off track for on-time graduation.",
    ]
    alerts = progress_report.get("alerts", [])
    if alerts:
        lines.append(f"Main blockers: {', '.join(alerts[:3])}.")
    actions = progress_report.get("recommended_actions", [])
    if actions:
        lines.append(f"Recommended next step: {actions[0]}")
    lines.append("Please review this plan with your counselor.")
    return " ".join(lines)


def generate_on_track_ai_insight(student, progress_report):
    api_key = os.environ.get("GEMINI_API_KEY")
    model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_TEXT_MODEL)

    if not settings.AI_ENABLED or not api_key:
        return _rule_based_on_track_insight(progress_report)

    context = {
        "student_name": f"{student.firstName} {student.lastName}",
        "grade_level": student.gradeLevel,
        "district": student.district.name if student.district else "",
        "progress_report": progress_report,
    }
    user_prompt = (
        "Give a short, practical action plan (3-5 sentences) for this student based only on this data. "
        "Focus on how they can get back on track before graduation."
    )
    messages = [{"role": "user", "content": user_prompt}]
    context_message = "Graduation progress context in JSON:\n" + json.dumps(
        context, ensure_ascii=True
    )

    try:
        return _call_gemini(api_key, model, context_message, messages)
    except (error.URLError, error.HTTPError, KeyError, ValueError, TimeoutError):
        return _rule_based_on_track_insight(progress_report)


def _call_gemini(api_key, model, context_message, messages):
    return call_gemini_text(
        api_key=api_key,
        model=model,
        system_prompt=SYSTEM_PROMPT,
        context_message=context_message,
        messages=messages,
        temperature=0.4,
    )


def generate_ai_advisor_reply(student, user_message, conversation_history):
    snapshot = build_student_academic_snapshot(student)
    api_key = os.environ.get("GEMINI_API_KEY")
    model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_TEXT_MODEL)

    if not settings.AI_ENABLED or not api_key:
        return AdvisorReply(_rule_based_fallback(snapshot, user_message), snapshot)

    context_message = "Student data snapshot in JSON. Use only this data:\n" + json.dumps(
        snapshot, ensure_ascii=True
    )
    history = conversation_history[-8:] if conversation_history else []
    messages = []
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    try:
        answer = _call_gemini(api_key, model, context_message, messages)
    except Exception as exc:
        # Only the provider boundary is guarded; do not expose exception details or keys.
        logger.warning("Gemini advisor request failed (%s).", type(exc).__name__)
        return AdvisorReply(_rule_based_fallback(snapshot, user_message), snapshot, api_failed=True)
    return AdvisorReply(answer, snapshot)
