from django.contrib.auth.views import LogoutView
from django.urls import path

from .views import auth, chat, counselor, parent, student

urlpatterns = [
    path("", auth.login_view, name="home"),
    path("login/", auth.login_view, name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("signup/counselor/", auth.managed_signup, name="counselor_signup"),
    path("signup/parent/", auth.managed_signup, name="parent_signup"),
    path("dashboard/", student.dashboard, name="dashboard"),
    path("dashboard/ai-chatbot/", chat.ai_chatbot, name="ai_chatbot"),
    path("dashboard/ai-chatbot/message/", chat.ai_chatbot_message, name="ai_chatbot_message"),
    path("dashboard/planner/", student.next_year_planner, name="next_year_planner"),
    path("dashboard/messages/", student.student_messages, name="student_messages"),
    path("counselor/dashboard/", counselor.counselor_dashboard, name="counselor_dashboard"),
    path(
        "counselor/requests/<int:request_id>/review/",
        counselor.review_course_request,
        name="review_course_request",
    ),
    path(
        "counselor/students/<int:student_id>/",
        counselor.counselor_student_profile,
        name="counselor_student_profile",
    ),
    path(
        "counselor/students/<int:student_id>/add-course/", counselor.add_course, name="add_course"
    ),
    path("counselor/messages/", counselor.counselor_messages, name="counselor_messages"),
    path(
        "counselor/messages/<int:student_id>/",
        counselor.counselor_messages,
        name="counselor_messages_with_student",
    ),
    path(
        "counselor/parent-messages/",
        counselor.counselor_parent_messages,
        name="counselor_parent_messages",
    ),
    path(
        "counselor/parent-messages/<int:conversation_id>/",
        counselor.counselor_parent_messages,
        name="counselor_parent_messages_with_conversation",
    ),
    path("parent/dashboard/", parent.parent_dashboard, name="parent_dashboard"),
    path("parent/messages/", parent.parent_messages, name="parent_messages"),
    path(
        "parent/messages/<int:student_id>/",
        parent.parent_messages,
        name="parent_messages_with_student",
    ),
    path("parent/ai-chatbot/", chat.parent_ai_chatbot, name="parent_ai_chatbot"),
    path(
        "parent/ai-chatbot/<int:student_id>/",
        chat.parent_ai_chatbot,
        name="parent_ai_chatbot_with_student",
    ),
    path(
        "parent/ai-chatbot/message/",
        chat.parent_ai_chatbot_message,
        name="parent_ai_chatbot_message",
    ),
    path("signup/", auth.signup, name="signup"),
    path("student/select-district/", student.select_district, name="select_district"),
]
