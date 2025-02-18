from django.http import HttpResponse
import datetime
from datetime import datetime

from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import User
from django.db import connection
from django.http import HttpResponseNotFound, HttpResponseServerError, HttpResponseBadRequest
from django.shortcuts import redirect, render

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

    messages = []
    # removed the "flagged = 0"-filter as nothing is flagged anyway
    unflagged = models.Message.objects.order_by("-pub_date")

    followers = models.Follower.objects.filter(who_id=request.user.id).values()

    # Convert to list of dicts
    # followers = [ dict(follower) for follower in list(followers) ]

    # Add the messages of followed users
    for follower in followers:
        # print(follower)
        follower_messages = unflagged.filter(user__id=follower["whom_id_id"])[
            :amount
        ].values()
        messages.extend(follower_messages)

    # Add the messages of the user
    # print(messages)
    user_messages = unflagged.filter(user__id=request.user.id)[
        :amount].values()
    messages.extend(user_messages)

    # Convert to list of dicts
    messages = [dict(message) for message in list(messages)]

    for message in messages:
        message["username"] = User.objects.get(id=message["user_id"])

    context = {"messages": messages, "amount": PER_PAGE + amount, "test": path}
    return render(request, "../templates/timeline.html", context)


def front_page_timeline(request):
    return timeline(request, "/timeline")


def main_timeline(request, amount=PER_PAGE):
    return timeline(request, "/timeline", amount=amount)


def public_timeline(request, amount=PER_PAGE):
    """Displays the latest messages of all users."""
    # Fetch all messages
    messages = (
        models.Message.objects.order_by(
            "-pub_date")[:amount].values()
    )

    # Convert to list of dicts
    messages = [dict(message) for message in list(messages)]

    # Add user info to each message

    for message in messages:
        message["username"] = User.objects.get(id=message["user_id"])

    context = {"messages": messages,
               "amount": amount, "test": "/public"}
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
    # print(messages)
    # Add user info to each message

    for message in messages:
        message["username"] = User.objects.get(id=message["user_id"])

    # print(messages)
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
        followed = True
    except:
        followed = False

    if followed:
        follow.delete()
    else:
        models.Follower.objects.create(who_id=request.user, whom_id=user)

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
            return redirect("/")
    return render(request, "../templates/login.html", {})


# /register
def register(request):
    """Shows a users timeline or if no user is logged in it will
    redirect to the public timeline.  This timeline shows the user's
    messages as well as all the messages of followed users.
    """

    if request.user.is_authenticated:
        return redirect("/")

    error = None
    if request.method == "POST":
        if request.POST["password"] != request.POST["password2"]:
            error = "The passwords do not match"
        else:

            user = User.objects.create_user(
                request.POST["username"],
                request.POST["email"],
                request.POST["password"],
            )

            user.save()
            return redirect("login")
    return render(request, "../templates/register.html", {"error": error})


# /logout
def logout(request):
    """Logout"""
    auth_logout(request)
    return redirect("public")


def add_message(request):
    """Registers a new message for the user."""
    if request.user.is_authenticated:
        # Get text and strip whitespace
        text = request.POST.get("text", "").strip()

        if not text:  # if text is empty just redirect to public without adding message
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
