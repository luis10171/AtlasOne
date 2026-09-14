from Pathway.models import TranscriptEntry
from Pathway.services.academic_policy import is_in_progress, is_passed


def get_student_satisfied_course_ids(student):
    current_grade = int(student.gradeLevel or 12)
    entries = (
        TranscriptEntry.objects.filter(transcript__student=student)
        .select_related("course")
        .order_by("gradeTaken", "course__name")
    )

    passed_ids = set()
    in_progress_ids = set()
    for entry in entries:
        if is_in_progress(entry, current_grade):
            in_progress_ids.add(entry.course_id)
            continue
        if is_passed(entry):
            passed_ids.add(entry.course_id)

    return passed_ids, in_progress_ids


def build_next_year_planner(student):
    target_grade = min(12, int(student.gradeLevel) + 1)
    passed_ids, in_progress_ids = get_student_satisfied_course_ids(student)
    satisfied_ids = passed_ids.union(in_progress_ids)

    if not student.district:
        return {
            "target_grade": target_grade,
            "passed_ids": passed_ids,
            "in_progress_ids": in_progress_ids,
            "satisfied_ids": satisfied_ids,
            "eligible_courses": [],
            "blocked_courses": [],
        }

    district_courses = (
        student.district.courses.select_related("subject")
        .prefetch_related("prerequisites")
        .order_by("subject__name", "name")
    )

    eligible_courses = []
    blocked_courses = []
    for course in district_courses:
        if course.id in satisfied_ids:
            continue
        missing_prerequisites = [
            prereq for prereq in course.prerequisites.all() if prereq.id not in satisfied_ids
        ]
        payload = {
            "course": course,
            "prerequisites": list(course.prerequisites.all()),
            "missing_prerequisites": missing_prerequisites,
            "in_progress_prerequisites": [
                prereq
                for prereq in course.prerequisites.all()
                if prereq.id in in_progress_ids and prereq.id not in passed_ids
            ],
        }
        if missing_prerequisites:
            blocked_courses.append(payload)
        else:
            eligible_courses.append(payload)

    return {
        "target_grade": target_grade,
        "passed_ids": passed_ids,
        "in_progress_ids": in_progress_ids,
        "satisfied_ids": satisfied_ids,
        "eligible_courses": eligible_courses,
        "blocked_courses": blocked_courses,
    }


def get_missing_prerequisite_names(student, course):
    passed_ids, in_progress_ids = get_student_satisfied_course_ids(student)
    satisfied_ids = passed_ids.union(in_progress_ids)
    return [prereq.name for prereq in course.prerequisites.all() if prereq.id not in satisfied_ids]
