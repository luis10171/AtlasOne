import json
import logging
import os
import re

from django.conf import settings

from Pathway.services.advisor_reply import AdvisorReply
from Pathway.services.gemini import (
    DEFAULT_GEMINI_TEXT_MODEL,
    call_gemini_text,
)
from Pathway.services.snapshot import build_student_academic_snapshot

logger = logging.getLogger(__name__)

PARENT_SYSTEM_PROMPT = """
You are AtlasOne Parent Assistant for K-12 families.
You help parents and guardians understand one student's school progress.

Critical behavior:
1) Always use clear, simple language first; avoid jargon.
2) Be especially supportive for immigrant families unfamiliar with U.S. school terms.
3) If a school term appears, explain it briefly in plain words.
4) Reply in the same language the parent used unless they ask for another language.
5) Give practical next steps parents can take this week.
6) Never invent courses, grades, requirements, or policies.
7) If data is missing, say what is missing and what to ask the counselor.
8) End with a short reminder that final school decisions are made with guidance counselors.
""".strip()
PARENT_FALLBACK_LANGUAGE_KEYWORDS = {
    "es": ["spanish", "espanol", "castellano", "en espanol", "in spanish"],
    "fr": ["french", "francais", "en francais", "in french"],
    "pt": ["portuguese", "portugues", "em portugues", "in portuguese"],
}
PARENT_FALLBACK_TEXT = {
    "en": {
        "intro": "Here is a simple update for {student_name}.",
        "status": "Current status: {status} ({percent}% complete).",
        "summary_prefix": "",
        "gaps_prefix": "Main requirement gaps: {gap_text}.",
        "recommend_prefix": "Suggested next classes: {course_list}.",
        "clarify": "If any term is unclear, ask and I can explain it in simple language in your preferred language.",
        "confirm": "Please confirm final decisions with your student's guidance counselor.",
    },
    "es": {
        "intro": "Aqui tienes una actualizacion simple para {student_name}.",
        "status": "Estado actual: {status} ({percent}% completado).",
        "summary_prefix": "",
        "gaps_prefix": "Principales requisitos pendientes: {gap_text}.",
        "recommend_prefix": "Clases sugeridas: {course_list}.",
        "clarify": "Si algun termino no es claro, dimelo y lo explico en lenguaje simple.",
        "confirm": "Por favor confirma las decisiones finales con el consejero escolar del estudiante.",
    },
    "fr": {
        "intro": "Voici une mise a jour simple pour {student_name}.",
        "status": "Statut actuel: {status} ({percent}% complete).",
        "summary_prefix": "",
        "gaps_prefix": "Principaux ecarts a combler: {gap_text}.",
        "recommend_prefix": "Cours suggeres ensuite: {course_list}.",
        "clarify": "Si un terme n'est pas clair, dites-le et je peux l'expliquer simplement.",
        "confirm": "Veuillez confirmer les decisions finales avec le conseiller scolaire de l'eleve.",
    },
    "pt": {
        "intro": "Aqui esta uma atualizacao simples para {student_name}.",
        "status": "Status atual: {status} ({percent}% concluido).",
        "summary_prefix": "",
        "gaps_prefix": "Principais lacunas de requisitos: {gap_text}.",
        "recommend_prefix": "Proximas aulas sugeridas: {course_list}.",
        "clarify": "Se algum termo nao estiver claro, diga e eu explico de forma simples.",
        "confirm": "Confirme as decisoes finais com o orientador escolar do estudante.",
    },
}


def _detect_parent_fallback_language(user_message, preferred_language=""):
    combined = f"{preferred_language or ''} {user_message or ''}".lower()
    for language_code, keywords in PARENT_FALLBACK_LANGUAGE_KEYWORDS.items():
        if any(keyword in combined for keyword in keywords):
            return language_code
    if re.search(r"[\u0600-\u06FF]", str(user_message or "")):
        return "en"
    return "en"


def _parent_rule_based_fallback(snapshot, user_message, preferred_language=""):
    language_code = _detect_parent_fallback_language(
        user_message=user_message,
        preferred_language=preferred_language,
    )
    text_bundle = PARENT_FALLBACK_TEXT.get(language_code, PARENT_FALLBACK_TEXT["en"])
    student_name = snapshot.get("student_profile", {}).get("name", "your student")
    graduation = snapshot.get("graduation_status", {})
    recommendations = snapshot.get("recommended_courses", [])
    requirements = snapshot.get("graduation_requirements", [])
    remaining = [item for item in requirements if item.get("remaining_credits", 0) > 0]

    lines = [
        text_bundle["intro"].format(student_name=student_name),
        text_bundle["status"].format(
            status=graduation.get("status", "Unknown"),
            percent=graduation.get("completion_percent", 0),
        ),
    ]
    if graduation.get("summary"):
        summary_prefix = text_bundle.get("summary_prefix", "")
        if summary_prefix:
            lines.append(f"{summary_prefix} {graduation['summary']}")
        else:
            lines.append(graduation["summary"])
    if remaining:
        gap_text = ", ".join(
            f"{item['subject']} ({item['remaining_credits']} credits left)"
            for item in remaining[:3]
        )
        lines.append(text_bundle["gaps_prefix"].format(gap_text=gap_text))
    if recommendations:
        lines.append(
            text_bundle["recommend_prefix"].format(
                course_list=", ".join(item["name"] for item in recommendations[:3])
            )
        )
    lines.append(text_bundle["clarify"])
    lines.append(text_bundle["confirm"])
    return " ".join(lines)


def generate_parent_ai_reply(parent, student, user_message, conversation_history):
    snapshot = build_student_academic_snapshot(student)
    api_key = os.environ.get("GEMINI_API_KEY")
    model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_TEXT_MODEL)

    if not settings.AI_ENABLED or not api_key:
        return AdvisorReply(
            _parent_rule_based_fallback(
                snapshot,
                user_message,
                preferred_language=parent.preferredLanguage,
            ),
            snapshot,
        )

    context = {
        "parent": {
            "name": f"{parent.firstName} {parent.lastName}",
            "preferred_language": parent.preferredLanguage or "",
        },
        "student_snapshot": snapshot,
    }
    context_message = "Parent support context in JSON. Use only this student data:\n" + json.dumps(
        context, ensure_ascii=True
    )
    history = conversation_history[-8:] if conversation_history else []
    messages = [*history, {"role": "user", "content": user_message}]

    try:
        answer = call_gemini_text(
            api_key=api_key,
            model=model,
            system_prompt=PARENT_SYSTEM_PROMPT,
            context_message=context_message,
            messages=messages,
            temperature=0.35,
        )
    except Exception as exc:
        # Only the provider boundary is guarded; do not expose exception details or keys.
        logger.warning("Gemini parent advisor request failed (%s).", type(exc).__name__)
        return AdvisorReply(
            _parent_rule_based_fallback(
                snapshot,
                user_message,
                preferred_language=parent.preferredLanguage,
            ),
            snapshot,
            api_failed=True,
        )
    return AdvisorReply(answer, snapshot)
