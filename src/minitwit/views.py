from django.http import HttpResponse
import datetime
from datetime import datetime

from django.db.models import Q, Subquery, OuterRef
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import User
from django.db import connection
from django.http import HttpResponseNotFound, HttpResponseServerError, HttpResponseBadRequest
from django.shortcuts import redirect, render
from urllib.parse import urlencode
from django.contrib import messages

from . import models

# Helper functions

PER_PAGE = 30


def query_db(query, args=(), one=False):
    """Queries the database and returns a list of dictionaries."""
    with connection.cursor() as cursor:
        cursor.execute(query, args)
        rv = [
            dict((cursor.description[idx][0], value)
                 for idx, value in enumerate(row))
            for row in cursor.fetchall()
        ]
    return (rv[0] if rv else None) if one else rv


def get_user_id(username):
    """Convenience method to look up the id for a username."""
    with connection.cursor() as cursor:
        rv = cursor.execute(
            "select user_id from user where username = ?", [username]
        ).fetchone()
    return rv[0] if rv else None


def format_datetime(timestamp):
    """Format a timestamp for display."""
    return datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d @ %H:%M")


# Views
# /
def timeline(request, path, amount=PER_PAGE):
    """Shows a users timeline or if no user is logged in it will
    redirect to the public timeline.  This timeline shows the user's
    messages as well as all the messages of followed users.
    """

    # Standard Redirect to Public if not logged in
    if not request.user.is_authenticated:
        return redirect("public")

    user_id = request.user.id

    # Get messages from the user or from users they follow
    messages_db = models.Message.objects.filter(
        Q(user_id=user_id) |
        Q(user_id__in=models.Follower.objects.filter(
            who_id=user_id).values_list('whom_id', flat=True))
    ).select_related('user').order_by('-pub_date')[:PER_PAGE]

    # Prepare data for the template
    messages_with_users = [
        {
            "username": message.user.username,  # Ensures `message.username` works
            "text": message.text,
            "pub_date": message.pub_date,
        }
        for message in messages_db
    ]

    context = {"messages": messages_with_users,
               "amount": PER_PAGE + amount, "test": path,
               "flashes": messages.get_messages(request)}
    return render(request, "../templates/timeline.html", context)


def front_page_timeline(request):
    return timeline(request, "/timeline")


def main_timeline(request, amount=PER_PAGE):
    return timeline(request, "/timeline", amount=amount)


def public_timeline(request, amount=PER_PAGE):
    """Displays the latest messages of all users."""
    # Fetch all messages
    messages_list = (
        models.Message.objects.select_related("user")
        .order_by("-pub_date")[:amount]
        .values("id", "text", "pub_date", "flagged", "user_id", "user__username", "user__email")
    )

    # Convert to list of dicts
    messages_list = [dict(message) for message in list(messages_list)]

    # Add user info to each message

    for message in messages_list:
        message["username"] = message["user__username"]

    context = {"messages": messages_list,
               "amount": amount, "test": "/public",
               "error": messages.get_messages(request),
               "flashes": messages.get_messages(request)}
    return render(request, "../templates/timeline.html", context)


def user_timeline(request, username, amount=PER_PAGE):
    try:
        # We do we not use filter
        user = User.objects.get(username=username)
    except:
        return HttpResponseNotFound("Username does not exist")

    # Check following
    try:
        models.Follower.objects.filter(
            who_id=request.user.id, whom_id=user.id).get()
        followed = True
    except:
        followed = False

    # Fetch all messages
    messages = (
        models.Message.objects.filter(user__id=user.id)
        .order_by("-pub_date")[:amount]
        .values()
    )

    # Convert to list of dicts
    messages = [dict(message) for message in messages]

    # Add user info to each message
    for message in messages:
        message["username"] = user.username

    context = {
        "messages": messages,
        "followed": followed,
        "profile_user": user,
        "test": f"/{username}",
        "amount": amount + PER_PAGE,
    }
    return render(request, "../templates/timeline.html", context)


# /follow
def follow_user(request, username):
    """Adds the current user as follower of the given user."""

    if not request.user:
        return redirect("login/")

    try:
        user = User.objects.get(username=username)
    except:
        return HttpResponseNotFound("Username does not exist")

    try:
        models.Follower.objects.create(who_id=request.user, whom_id=user)
    except:
        return HttpResponseServerError("User already follows user")

    return redirect("user_timeline", username=username)

# /unfollow


def unfollow_user(request, username):
    """Adds the current user as follower of the given user."""

    if not request.user:
        return redirect("public/")

    try:
        user = User.objects.get(username=username)
    except:
        return HttpResponseNotFound("Username does not exist")

    try:
        follow = models.Follower.objects.filter(
            who_id=request.user, whom_id=user).get()
    except:
        return HttpResponseNotFound("Username does not exist")

    follow.delete()

    return redirect("user_timeline", username=username)


# /login
def login(request):
    """Login"""
    if request.user.is_authenticated:
        return redirect("/")

    if request.method == "POST":
        user = authenticate(
            username=request.POST["username"], password=request.POST["password"]
        )
        if user is None:
            return HttpResponseNotFound("Wrong credentials")
        else:
            auth_login(request, user)
            messages.info(request, "You were logged in")
            return redirect("/")
    return render(request, "../templates/login.html", {"flashes": messages.get_messages(request)})


# /register
def register(request):
    """Register"""
    if request.user.is_authenticated:
        return redirect("/")

    error = None
    if request.method == "POST":
        if request.POST["password"] != request.POST["password2"]:
            error = "The passwords do not match"
        else:
            try:
                User.objects.get(username=request.POST["username"])
                error = "Username already exists"
            except:
                user = User.objects.create_user(
                    request.POST["username"],
                    request.POST["email"],
                    request.POST["password"],
                )
                user.save()
                messages.info(
                    request, "You were successfully registered and can login now")
                return redirect("login")

    return render(request, "../templates/register.html", {"error": error})


# /logout
def logout(request):
    """Logout"""
    auth_logout(request)
    messages.info(request, "You were logged out")
    return redirect("public")


def add_message(request):
    """Registers a new message for the user."""
    if request.user.is_authenticated:
        # Get text and strip whitespace
        text = request.POST.get("text", "").strip()

        if not text:  # if text is empty just redirect to public without adding message
            messages.error(request, "Message cannot be empty")
            return redirect("public")

        message_object = models.Message.objects.create(
            user=request.user, text=text, flagged=0
        )

        message_object.save()
    else:
        return HttpResponseNotFound("User not logged in")
    return redirect("public")


def load_more_messages(request, last_message_id):
    # get the next 10 messages after the last message ID
    messages = models.Message.objects.filter(id__gt=last_message_id).order_by(
        "-pub_date"
    )[:10]

    # render the new messages as HTML'
    message_html = render(request, "message_list.html", {
                          "messages": messages}).content

    # return the new messages as an AJAX response
    return HttpResponse(message_html)
