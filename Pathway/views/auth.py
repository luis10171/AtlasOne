"""Authentication uses Django's validation and an atomic student signup."""

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm
from django.db import IntegrityError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from Pathway.access import home_for_user
from Pathway.forms import StudentSignupForm


@require_http_methods(["GET", "POST"])
def login_view(request):
    form = AuthenticationForm(request, data=request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        destination = home_for_user(user)
        if destination:
            login(request, user)
            return redirect(destination)
        form.add_error(None, "No profile is linked to this account. Contact school staff.")
    return render(request, "auth/login.html", {"form": form})


@require_http_methods(["GET", "POST"])
def signup(request):
    form = StudentSignupForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            user = form.save()
        except IntegrityError:
            form.add_error(None, "That account could not be created. Try a different username.")
        else:
            login(request, user)
            messages.success(request, "Account created. Choose your district to start planning.")
            return redirect("dashboard")
    return render(request, "auth/signup.html", {"form": form})


@require_http_methods(["GET", "POST"])
def managed_signup(request):
    return render(request, "auth/managed_signup.html", status=403)
