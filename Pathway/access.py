"""Object-level access rules shared by dashboards, transcripts, and messaging."""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.db.models import F, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect

from Pathway.models import (
    CounselorConversation,
    GuidanceCounselor,
    ParentCounselorConversation,
    Student,
)


def _student_or_none(user):
    return getattr(user, "student", None)


def _counselor_or_none(user):
    return getattr(user, "guidancecounselor", None)


def _parent_or_none(user):
    return getattr(user, "parent", None)


def home_for_user(user):
    if user.is_staff:
        return "admin:index"
    if _counselor_or_none(user):
        return "counselor_dashboard"
    if _parent_or_none(user):
        return "parent_dashboard"
    if _student_or_none(user):
        return "dashboard"
    return None


def _require_profile(relation, request_attribute):
    def decorate(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            profile = getattr(request.user, relation, None)
            if profile is None:
                destination = home_for_user(request.user)
                if destination:
                    return redirect(destination)
                raise Http404("No profile is linked to this account.")
            setattr(request, request_attribute, profile)
            return view(request, *args, **kwargs)

        return wrapped

    return decorate


student_required = _require_profile("student", "student")
counselor_required = _require_profile("guidancecounselor", "counselor")
parent_required = _require_profile("parent", "parent_profile")


def _get_counselor_students(counselor):
    access = Q(assignedCounselor=counselor)
    if counselor.district_id:
        access |= Q(district_id=counselor.district_id)
    return (
        Student.objects.filter(access)
        .select_related("district", "user", "assignedCounselor__user")
        .order_by("lastName", "firstName")
    )


def counselors_for_student(student):
    access = Q(pk=student.assignedCounselor_id) if student.assignedCounselor_id else Q(pk__in=[])
    if student.district_id:
        access |= Q(district_id=student.district_id)
    return (
        GuidanceCounselor.objects.filter(access)
        .select_related("district", "user")
        .order_by("lastName", "firstName")
    )


def _get_parent_linked_students(parent):
    return (
        Student.objects.filter(parent_links__parent=parent)
        .select_related("district", "user", "assignedCounselor__user")
        .order_by("lastName", "firstName")
    )


def _resolve_student_counselor(student):
    # Assignment is a staff decision. Reading a page must not assign a counselor.
    return student.assignedCounselor


def counselor_conversations(counselor):
    return CounselorConversation.objects.filter(
        counselor=counselor, student__in=_get_counselor_students(counselor)
    ).select_related("student__user")


def parent_conversations(counselor):
    # Re-check current links and assignment; an old thread is not an access grant.
    return ParentCounselorConversation.objects.filter(
        counselor=counselor,
        student__assignedCounselor=counselor,
        student__parent_links__parent_id=F("parent_id"),
    ).select_related("parent__user", "student__user")


def record_or_404(queryset, value):
    """Handle identifiers from query parameters and form fields without a 500."""
    if isinstance(value, bool) or not str(value).isascii() or not str(value).isdigit():
        raise Http404("Record not found.")
    if len(str(value)) > 18 or int(value) <= 0:
        raise Http404("Record not found.")
    return get_object_or_404(queryset, pk=int(value))
