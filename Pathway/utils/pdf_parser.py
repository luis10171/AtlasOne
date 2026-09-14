"""Import the supported five-column transcript table layout for counselor review."""

import math
import re

import pdfplumber

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 20
MAX_TRANSCRIPT_ROWS = 100


def _normalize_course_name(value):
    return " ".join(str(value or "").split()).casefold()


def _number_or_none(value, converter):
    if value is None or not str(value).strip():
        return None
    try:
        number = converter(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def extract_courses_from_pdf(pdf_file, student, district_courses):
    if pdf_file.size > MAX_PDF_BYTES:
        raise ValueError("Transcript PDFs must be 10 MB or smaller.")
    if pdf_file.read(5) != b"%PDF-":
        raise ValueError("The uploaded file is not a PDF.")
    pdf_file.seek(0)

    lookup = {}
    for course in district_courses:
        name = _normalize_course_name(course.name)
        # Duplicate display names require manual selection; never guess a course.
        lookup[name] = None if name in lookup else course

    entries = []
    freshman_year = student.graduationYear - 4
    grade_level = student.gradeLevel

    with pdfplumber.open(pdf_file) as pdf:
        if len(pdf.pages) > MAX_PDF_PAGES:
            raise ValueError(f"Transcripts may contain at most {MAX_PDF_PAGES} pages.")
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for row in table:
                    if not row or not any(row):
                        continue
                    course_name, _level, final_grade, credits_earned, _attempted = (
                        list(row) + [None] * 5
                    )[:5]
                    name = " ".join(str(course_name or "").split())
                    academic_year = re.fullmatch(r"(\d{4})\s*-\s*(\d{4})", name)
                    if academic_year:
                        grade_level = 9 + int(academic_year[1]) - freshman_year
                        continue
                    if not name or name.upper() in {"COURSE", "TOTAL", "GRAND TOTAL"}:
                        continue
                    course = lookup.get(_normalize_course_name(name))
                    entries.append(
                        {
                            "course_id": course.id if course else None,
                            "course_name": name,
                            # Unknown values stay blank so the review form demands a correction.
                            "grade": _number_or_none(final_grade, int),
                            "credits": _number_or_none(credits_earned, float),
                            "grade_taken": grade_level,
                        }
                    )
                    if len(entries) > MAX_TRANSCRIPT_ROWS:
                        raise ValueError(
                            f"Transcripts may contain at most {MAX_TRANSCRIPT_ROWS} rows."
                        )
    return entries
