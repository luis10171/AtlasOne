from django.contrib import admin

from .models import (
    CounselorConversation,
    CounselorMessage,
    Course,
    CourseRequest,
    District,
    GraduationRequirement,
    GuidanceCounselor,
    Parent,
    ParentCounselorConversation,
    ParentCounselorMessage,
    ParentStudentLink,
    Student,
    Subject,
)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("name", "subject", "creditValue", "isCoreClass")
    list_filter = ("subject", "isCoreClass")
    search_fields = ("name",)
    filter_horizontal = ("prerequisites",)


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ("name", "state")
    search_fields = ("name", "state")
    filter_horizontal = ("courses",)


@admin.register(GraduationRequirement)
class GraduationRequirementAdmin(admin.ModelAdmin):
    list_display = ("district", "subject", "requiredCredits")
    list_filter = ("district",)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "firstName",
        "lastName",
        "gradeLevel",
        "graduationYear",
        "district",
        "assignedCounselor",
    )
    search_fields = ("firstName", "lastName", "user__username")
    list_filter = ("district", "assignedCounselor")


@admin.register(GuidanceCounselor)
class GuidanceCounselorAdmin(admin.ModelAdmin):
    list_display = ("user", "firstName", "lastName", "district")
    search_fields = ("firstName", "lastName", "user__username")
    list_filter = ("district",)


@admin.register(CourseRequest)
class CourseRequestAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "course",
        "requested_for_grade",
        "status",
        "reviewed_by",
        "created_at",
    )
    list_filter = ("status", "requested_for_grade", "course__subject")
    search_fields = (
        "student__firstName",
        "student__lastName",
        "course__name",
        "student__user__username",
    )


@admin.register(CounselorConversation)
class CounselorConversationAdmin(admin.ModelAdmin):
    list_display = ("student", "counselor", "updated_at")
    list_filter = ("counselor",)
    search_fields = ("student__firstName", "student__lastName", "counselor__user__username")


@admin.register(CounselorMessage)
class CounselorMessageAdmin(admin.ModelAdmin):
    list_display = ("conversation", "sender", "created_at")
    search_fields = (
        "conversation__student__firstName",
        "conversation__student__lastName",
        "sender__username",
        "body",
    )


@admin.register(Parent)
class ParentAdmin(admin.ModelAdmin):
    list_display = ("user", "firstName", "lastName", "preferredLanguage")
    search_fields = ("firstName", "lastName", "user__username", "user__email")


@admin.register(ParentStudentLink)
class ParentStudentLinkAdmin(admin.ModelAdmin):
    list_display = ("parent", "student", "relationship", "created_at")
    list_filter = ("relationship",)
    search_fields = (
        "parent__firstName",
        "parent__lastName",
        "student__firstName",
        "student__lastName",
    )


@admin.register(ParentCounselorConversation)
class ParentCounselorConversationAdmin(admin.ModelAdmin):
    list_display = ("parent", "student", "counselor", "updated_at")
    list_filter = ("counselor",)
    search_fields = (
        "parent__firstName",
        "parent__lastName",
        "student__firstName",
        "student__lastName",
    )


@admin.register(ParentCounselorMessage)
class ParentCounselorMessageAdmin(admin.ModelAdmin):
    list_display = ("conversation", "sender", "created_at")
    search_fields = (
        "conversation__parent__firstName",
        "conversation__student__firstName",
        "sender__username",
        "body",
    )
