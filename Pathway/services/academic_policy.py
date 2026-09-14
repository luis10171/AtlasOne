"""Shared prototype grading policy; district-specific policies are not modeled yet."""

PASSING_GRADE = 60


def is_passed(entry):
    return entry.grade >= PASSING_GRADE and entry.creditsEarned > 0


def is_in_progress(entry, current_grade):
    # Legacy transcripts use this sentinel until enrollment status is modeled.
    return entry.gradeTaken == current_grade and entry.grade == 0 and entry.creditsEarned == 0
