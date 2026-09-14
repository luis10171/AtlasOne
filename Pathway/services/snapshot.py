"""Build the structured academic context shared by both advisor roles."""

from Pathway.models import GraduationRequirement, TranscriptEntry
from Pathway.services.academic_policy import is_in_progress, is_passed
from Pathway.services.graduation import GraduationEngine


def build_student_academic_snapshot(student):
    graduation_status = GraduationEngine(student).build_progress_report()
    entries = list(
        TranscriptEntry.objects.filter(transcript__student=student)
        .select_related("course__subject")
        .order_by("gradeTaken", "course__name")
    )
    current_grade = int(student.gradeLevel)

    passed_entries = []
    in_progress_entries = []
    for entry in entries:
        if is_in_progress(entry, current_grade):
            in_progress_entries.append(entry)
            continue
        if is_passed(entry):
            passed_entries.append(entry)

    passed_course_ids = {entry.course_id for entry in passed_entries}
    in_progress_course_ids = {entry.course_id for entry in in_progress_entries}
    taken_course_ids = passed_course_ids.union(in_progress_course_ids)

    subject_stats = {}
    for entry in passed_entries:
        subject_id = entry.course.subject_id
        subject_name = entry.course.subject.name
        stats = subject_stats.setdefault(
            subject_id,
            {
                "course__subject_id": subject_id,
                "course__subject__name": subject_name,
                "earned_credits": 0.0,
                "grade_sum": 0.0,
                "course_count": 0,
            },
        )
        stats["earned_credits"] += float(entry.creditsEarned or 0.0)
        stats["grade_sum"] += float(entry.grade or 0.0)
        stats["course_count"] += 1

    subject_rollup = []
    for item in subject_stats.values():
        avg_grade = item["grade_sum"] / item["course_count"] if item["course_count"] > 0 else None
        subject_rollup.append(
            {
                "course__subject_id": item["course__subject_id"],
                "course__subject__name": item["course__subject__name"],
                "earned_credits": item["earned_credits"],
                "avg_grade": avg_grade,
                "course_count": item["course_count"],
            }
        )

    requirements = list(
        GraduationRequirement.objects.filter(district=student.district).select_related("subject")
    )
    requirement_summary = []
    for requirement in requirements:
        earned = float(subject_stats.get(requirement.subject_id, {}).get("earned_credits") or 0.0)
        required = float(requirement.requiredCredits)
        remaining = max(required - earned, 0.0)
        requirement_summary.append(
            {
                "subject": requirement.subject.name,
                "required_credits": round(required, 2),
                "earned_credits": round(earned, 2),
                "remaining_credits": round(remaining, 2),
            }
        )

    district_courses = (
        student.district.courses.select_related("subject")
        .prefetch_related("prerequisites")
        .order_by("subject__name", "name")
    )

    eligible_courses = []
    blocked_courses = []
    for course in district_courses:
        if course.id in taken_course_ids:
            continue
        prereq_names = [prereq.name for prereq in course.prerequisites.all()]
        missing = [
            prereq.name
            for prereq in course.prerequisites.all()
            if prereq.id not in passed_course_ids and prereq.id not in in_progress_course_ids
        ]
        in_progress_prereqs = [
            prereq.name
            for prereq in course.prerequisites.all()
            if prereq.id in in_progress_course_ids and prereq.id not in passed_course_ids
        ]
        course_payload = {
            "name": course.name,
            "subject": course.subject.name,
            "credit_value": float(course.creditValue),
            "is_core_class": bool(course.isCoreClass),
            "prerequisites": prereq_names,
            "missing_prerequisites": missing,
            "in_progress_prerequisites": in_progress_prereqs,
        }
        if missing or in_progress_prereqs:
            blocked_courses.append(course_payload)
        else:
            eligible_courses.append(course_payload)

    top_recommendations = []
    scored = []
    stats_by_subject = {row["course__subject__name"]: row for row in subject_rollup}
    gaps_by_subject = {row["subject"]: row["remaining_credits"] for row in requirement_summary}
    for course in eligible_courses:
        stats = stats_by_subject.get(course["subject"])
        avg_grade = float(stats["avg_grade"]) if stats and stats["avg_grade"] else 78.0
        gap = float(gaps_by_subject.get(course["subject"], 0.0))
        score = (avg_grade / 100.0) * 2.0 + min(gap, 4.0)
        if course["is_core_class"]:
            score += 2.5
        reasons = []
        if gap > 0:
            reasons.append(f"helps close {gap:.1f} remaining {course['subject']} credits")
        if course["is_core_class"]:
            reasons.append("is marked as a required core class by your district")
        if avg_grade >= 85:
            reasons.append(f"matches your strong performance in {course['subject']}")
        if not course["prerequisites"]:
            reasons.append("has no prerequisites")
        elif not course["missing_prerequisites"]:
            reasons.append("all prerequisites are already complete")
        scored.append((score, course, reasons))

    for _, course, reasons in sorted(scored, key=lambda item: item[0], reverse=True)[:8]:
        top_recommendations.append(
            {
                "name": course["name"],
                "subject": course["subject"],
                "credit_value": course["credit_value"],
                "is_core_class": course["is_core_class"],
                "why": reasons[:2] or ["fits your current schedule options"],
            }
        )

    missing_core_courses = sorted(
        [
            {
                "name": course["name"],
                "subject": course["subject"],
                "credit_value": course["credit_value"],
            }
            for course in eligible_courses + blocked_courses
            if course["is_core_class"]
        ],
        key=lambda course: (course["subject"], course["name"]),
    )

    in_progress_entry_ids = {entry.pk for entry in in_progress_entries}
    passed_entry_ids = {entry.pk for entry in passed_entries}
    taken_courses = [
        {
            "name": entry.course.name,
            "subject": entry.course.subject.name,
            "grade": entry.grade,
            "credits_earned": float(entry.creditsEarned),
            "grade_taken": entry.gradeTaken,
            "status": (
                "in_progress"
                if entry.pk in in_progress_entry_ids
                else ("completed" if entry.pk in passed_entry_ids else "not_passed")
            ),
        }
        for entry in entries
    ]

    strengths = sorted(
        [
            {
                "subject": item["course__subject__name"],
                "avg_grade": round(float(item["avg_grade"]), 1)
                if item["avg_grade"] is not None
                else None,
                "earned_credits": round(float(item["earned_credits"] or 0.0), 1),
            }
            for item in subject_rollup
        ],
        key=lambda row: row["avg_grade"] if row["avg_grade"] is not None else 0.0,
        reverse=True,
    )

    return {
        "student_profile": {
            "name": f"{student.firstName} {student.lastName}",
            "grade_level": student.gradeLevel,
            "graduation_year": student.graduationYear,
            "gpa": float(student.GPA),
            "district": student.district.name,
            "district_state": student.district.state,
        },
        "graduation_status": {
            "on_track": graduation_status["on_track"],
            "status": graduation_status["status"],
            "summary": graduation_status["summary"],
            "completion_percent": graduation_status["completion_percent"],
            "years_remaining": graduation_status["years_remaining"],
            "course_slots_remaining": graduation_status["course_slots_remaining"],
            "minimum_courses_needed": graduation_status["minimum_courses_needed"],
            "alerts": graduation_status["alerts"][:6],
            "recommended_actions": graduation_status["recommended_actions"][:5],
        },
        "in_progress_courses": [
            {
                "name": entry.course.name,
                "subject": entry.course.subject.name,
                "grade_taken": entry.gradeTaken,
                "projected_credits": float(entry.course.creditValue or 0.0),
            }
            for entry in in_progress_entries
        ],
        "taken_courses": taken_courses,
        "subject_strengths": strengths,
        "graduation_requirements": requirement_summary,
        "recommended_courses": top_recommendations,
        "eligible_courses": eligible_courses[:30],
        "blocked_courses": blocked_courses[:30],
        "missing_core_courses": missing_core_courses[:30],
    }
