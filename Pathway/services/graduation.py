import math
from collections import Counter, defaultdict

from Pathway.models import GraduationRequirement, TranscriptEntry
from Pathway.services.academic_policy import is_in_progress, is_passed


class GraduationEngine:
    def __init__(self, student):
        self.student = student

    def _years_remaining(self):
        try:
            grade = int(self.student.gradeLevel)
        except (TypeError, ValueError):
            grade = 12
        return max(0, 13 - grade)

    def _all_entries(self):
        return list(
            TranscriptEntry.objects.filter(transcript__student=self.student)
            .select_related("course__subject")
            .prefetch_related("course__prerequisites")
        )

    def _passed_entries(self, entries):
        return [entry for entry in entries if is_passed(entry)]

    def _in_progress_entries(self, entries):
        return [entry for entry in entries if is_in_progress(entry, self.student.gradeLevel)]

    def _estimate_annual_course_capacity(self, entries, district_course_count):
        if not entries:
            historical_average = 0
            historical_peak = 0
        else:
            counts_by_grade = Counter(
                int(entry.gradeTaken) for entry in entries if entry.gradeTaken
            )
            historical_peak = max(counts_by_grade.values()) if counts_by_grade else 0
            historical_average = (
                math.ceil(sum(counts_by_grade.values()) / len(counts_by_grade))
                if counts_by_grade
                else 0
            )

        if district_course_count > 0:
            district_baseline = max(2, min(8, math.ceil(district_course_count / 4)))
        else:
            district_baseline = 4

        return max(1, district_baseline, historical_average, historical_peak)

    def build_progress_report(self):
        if not self.student.district:
            return {
                "on_track": False,
                "status": "Off Track",
                "summary": "District not selected. Graduation requirements cannot be evaluated yet.",
                "years_remaining": self._years_remaining(),
                "annual_course_capacity": 0,
                "course_slots_remaining": 0,
                "minimum_courses_needed": 0,
                "completion_percent": 0,
                "subject_requirements": [],
                "core_requirements": [],
                "alerts": ["Select a district to load graduation requirements."],
                "recommended_actions": [
                    "Select your school district first so requirements and course options can be calculated."
                ],
            }

        entries = self._all_entries()
        passed_entries = self._passed_entries(entries)
        in_progress_entries = self._in_progress_entries(entries)
        passed_course_ids = {entry.course_id for entry in passed_entries}
        in_progress_course_ids = {entry.course_id for entry in in_progress_entries}
        requirements = list(
            GraduationRequirement.objects.filter(district=self.student.district).select_related(
                "subject"
            )
        )
        district_courses = list(
            self.student.district.courses.select_related("subject").prefetch_related(
                "prerequisites"
            )
        )
        district_course_map = {course.id: course for course in district_courses}

        earned_by_subject = defaultdict(float)
        for entry in passed_entries:
            earned_by_subject[entry.course.subject_id] += float(entry.creditsEarned or 0.0)
        projected_in_progress_by_subject = defaultdict(float)
        for entry in in_progress_entries:
            projected_in_progress_by_subject[entry.course.subject_id] += float(
                entry.course.creditValue or 0.0
            )

        remaining_by_subject = {}
        subject_requirements = []
        for requirement in requirements:
            earned = float(earned_by_subject.get(requirement.subject_id, 0.0))
            projected = float(projected_in_progress_by_subject.get(requirement.subject_id, 0.0))
            required = float(requirement.requiredCredits)
            remaining = max(0.0, required - earned - projected)
            remaining_by_subject[requirement.subject_id] = remaining
            subject_requirements.append(
                {
                    "subject": requirement.subject.name,
                    "subject_id": requirement.subject_id,
                    "required": round(required, 2),
                    "earned": round(earned, 2),
                    "in_progress_credits": round(projected, 2),
                    "remaining": round(remaining, 2),
                }
            )

        can_complete_cache = {}

        def can_complete_course(course_id, stack=None):
            if course_id in passed_course_ids or course_id in in_progress_course_ids:
                return True
            if course_id not in district_course_map:
                return False
            if course_id in can_complete_cache:
                return can_complete_cache[course_id]

            if stack is None:
                stack = set()
            if course_id in stack:
                can_complete_cache[course_id] = False
                return False

            stack.add(course_id)
            course = district_course_map[course_id]
            for prereq in course.prerequisites.all():
                if prereq.id in passed_course_ids or prereq.id in in_progress_course_ids:
                    continue
                if not can_complete_course(prereq.id, stack):
                    can_complete_cache[course_id] = False
                    stack.remove(course_id)
                    return False
            stack.remove(course_id)
            can_complete_cache[course_id] = True
            return True

        available_by_subject = defaultdict(float)
        for course in district_courses:
            if course.id in passed_course_ids or course.id in in_progress_course_ids:
                continue
            if not can_complete_course(course.id):
                continue
            available_by_subject[course.subject_id] += float(course.creditValue or 0.0)

        for item in subject_requirements:
            available = float(available_by_subject.get(item["subject_id"], 0.0))
            item["available_remaining_credits"] = round(available, 2)
            item["can_still_meet"] = item["remaining"] <= round(available, 2) + 1e-9

        required_core_courses = sorted(
            [course for course in district_courses if course.isCoreClass],
            key=lambda course: course.name,
        )
        core_requirements = []
        for course in required_core_courses:
            completed = course.id in passed_course_ids
            in_progress = course.id in in_progress_course_ids
            missing_prerequisites = sorted(
                [
                    prereq.name
                    for prereq in course.prerequisites.all()
                    if prereq.id not in passed_course_ids
                    and prereq.id not in in_progress_course_ids
                ]
            )
            core_requirements.append(
                {
                    "course_id": course.id,
                    "name": course.name,
                    "subject": course.subject.name,
                    "credit_value": float(course.creditValue),
                    "completed": completed,
                    "in_progress": in_progress,
                    "missing_prerequisites": missing_prerequisites,
                    "can_still_complete": completed
                    or in_progress
                    or can_complete_course(course.id),
                }
            )

        selected_course_ids = set(in_progress_course_ids)
        planning_issues = []

        def include_course_with_prereqs(course_id, stack=None):
            if (
                course_id in passed_course_ids
                or course_id in in_progress_course_ids
                or course_id in selected_course_ids
            ):
                return True
            if course_id not in district_course_map:
                return False

            if stack is None:
                stack = set()
            if course_id in stack:
                return False

            stack.add(course_id)
            course = district_course_map[course_id]
            for prereq in course.prerequisites.all():
                if (
                    prereq.id in passed_course_ids
                    or prereq.id in in_progress_course_ids
                    or prereq.id in selected_course_ids
                ):
                    continue
                if not include_course_with_prereqs(prereq.id, stack):
                    stack.remove(course_id)
                    return False
            selected_course_ids.add(course_id)
            stack.remove(course_id)
            return True

        for core_item in core_requirements:
            if core_item["completed"] or core_item["in_progress"]:
                continue
            if not include_course_with_prereqs(core_item["course_id"], set()):
                planning_issues.append(
                    f"Required core class '{core_item['name']}' cannot be completed with the currently configured district courses."
                )

        planned_remaining = dict(remaining_by_subject)

        def apply_newly_selected_credits(new_ids):
            for new_id in new_ids:
                course = district_course_map.get(new_id)
                if not course:
                    continue
                subject_id = course.subject_id
                if subject_id not in planned_remaining:
                    continue
                planned_remaining[subject_id] = max(
                    0.0,
                    float(planned_remaining[subject_id]) - float(course.creditValue or 0.0),
                )

        apply_newly_selected_credits(set(selected_course_ids))

        subject_candidates = defaultdict(list)
        for course in district_courses:
            if course.id in passed_course_ids or course.id in in_progress_course_ids:
                continue
            subject_candidates[course.subject_id].append(course)
        for subject_id in subject_candidates:
            subject_candidates[subject_id].sort(
                key=lambda course: (float(course.creditValue), course.name),
                reverse=True,
            )

        while True:
            unresolved_subject_ids = [
                subject_id
                for subject_id, remaining in planned_remaining.items()
                if remaining > 1e-9
            ]
            if not unresolved_subject_ids:
                break

            made_progress = False
            for subject_id in unresolved_subject_ids:
                candidates = subject_candidates.get(subject_id, [])
                for candidate in candidates:
                    if candidate.id in selected_course_ids:
                        continue
                    before = set(selected_course_ids)
                    if include_course_with_prereqs(candidate.id, set()):
                        apply_newly_selected_credits(selected_course_ids - before)
                        made_progress = True
                        break
            if not made_progress:
                break

        unresolved_credit_gaps = []
        for requirement in requirements:
            remaining_after_plan = float(planned_remaining.get(requirement.subject_id, 0.0))
            if remaining_after_plan > 1e-9:
                unresolved_credit_gaps.append(
                    {
                        "subject": requirement.subject.name,
                        "remaining": round(remaining_after_plan, 2),
                    }
                )

        years_remaining = self._years_remaining()
        annual_course_capacity = self._estimate_annual_course_capacity(
            entries=entries,
            district_course_count=len(district_courses),
        )
        course_slots_remaining = years_remaining * annual_course_capacity
        in_progress_count = len(in_progress_course_ids)
        future_course_slots_remaining = max(0, course_slots_remaining - in_progress_count)
        minimum_courses_needed = max(0, len(selected_course_ids) - in_progress_count)
        has_time_capacity = minimum_courses_needed <= future_course_slots_remaining

        total_required_credits = sum(float(req.requiredCredits) for req in requirements)
        earned_toward_required = 0.0
        for req in requirements:
            earned_toward_required += min(
                float(req.requiredCredits),
                float(earned_by_subject.get(req.subject_id, 0.0)),
            )
        total_core_count = len(core_requirements)
        completed_core_count = sum(1 for core in core_requirements if core["completed"])
        completion_denom = total_required_credits + total_core_count
        if completion_denom <= 0:
            completion_percent = 100
        else:
            completion_percent = int(
                round(100 * ((earned_toward_required + completed_core_count) / completion_denom))
            )

        on_track = (
            len(planning_issues) == 0 and len(unresolved_credit_gaps) == 0 and has_time_capacity
        )

        alerts = []
        for item in subject_requirements:
            if item["remaining"] > 0:
                alerts.append(f"Missing {item['remaining']} credits in {item['subject']}")
        for item in core_requirements:
            if not item["completed"] and not item["in_progress"]:
                alerts.append(f"Missing required core class: {item['name']}")
        for issue in planning_issues:
            alerts.append(issue)
        if not has_time_capacity and minimum_courses_needed > 0:
            alerts.append(
                f"Current graduation plan needs at least {minimum_courses_needed} additional courses, "
                f"but only about {future_course_slots_remaining} open course slots remain before graduation."
            )

        recommended_actions = []
        if alerts:
            for item in core_requirements:
                if item["completed"] or item["in_progress"]:
                    continue
                if item["missing_prerequisites"]:
                    prereq_text = ", ".join(item["missing_prerequisites"][:3])
                    recommended_actions.append(
                        f"Schedule prerequisites for {item['name']} first: {prereq_text}."
                    )
                else:
                    recommended_actions.append(
                        f"Prioritize {item['name']} in your next available term."
                    )

            for gap in unresolved_credit_gaps[:3]:
                recommended_actions.append(
                    f"Add more {gap['subject']} courses. Remaining shortfall after current plan: {gap['remaining']} credits."
                )

            if years_remaining > 0 and minimum_courses_needed > 0:
                courses_per_year = math.ceil(minimum_courses_needed / years_remaining)
                recommended_actions.append(
                    f"Plan for about {courses_per_year} graduation-relevant courses per year for the next {years_remaining} year(s)."
                )
            elif minimum_courses_needed > 0:
                recommended_actions.append(
                    "Meet with your counselor immediately to discuss a credit recovery or extended timeline plan."
                )

            if planning_issues:
                recommended_actions.append(
                    "Ask your counselor or district admin to verify missing prerequisites and district course availability."
                )

        if on_track:
            status = "On Track"
            summary = (
                f"You are on track to graduate. Estimated plan needs {minimum_courses_needed} more course(s) "
                f"across the next {years_remaining} year(s)."
            )
        else:
            status = "Off Track"
            summary = (
                "You are currently off track to graduate on time based on transcript progress, "
                "district requirements, and remaining schedule capacity."
            )

        return {
            "on_track": on_track,
            "status": status,
            "summary": summary,
            "years_remaining": years_remaining,
            "annual_course_capacity": annual_course_capacity,
            "course_slots_remaining": course_slots_remaining,
            "future_course_slots_remaining": future_course_slots_remaining,
            "minimum_courses_needed": minimum_courses_needed,
            "completion_percent": max(0, min(completion_percent, 100)),
            "subject_requirements": subject_requirements,
            "core_requirements": core_requirements,
            "in_progress_courses": [
                {
                    "name": entry.course.name,
                    "subject": entry.course.subject.name,
                    "grade_taken": entry.gradeTaken,
                    "projected_credits": float(entry.course.creditValue or 0.0),
                }
                for entry in in_progress_entries
            ],
            "alerts": alerts,
            "recommended_actions": recommended_actions[:8],
        }

    def evaluateStudent(self, student=None):
        if student is not None:
            self.student = student
        return self.build_progress_report()

    def generateAlerts(self):
        return self.build_progress_report().get("alerts", [])
