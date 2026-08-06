from flask import request
from flask_login import current_user
from flask_socketio import join_room, leave_room
from app import socketio


@socketio.on("connect")
def on_connect():
    """When a client connects, put them in their personal room."""
    if current_user.is_authenticated:
        join_room(f"user_{current_user.id}")
        # Admins also join the shared admin room
        if current_user.is_admin or current_user.is_super_admin:
            join_room("admins")


@socketio.on("disconnect")
def on_disconnect():
    if current_user.is_authenticated:
        leave_room(f"user_{current_user.id}")
        if current_user.is_admin or current_user.is_super_admin:
            leave_room("admins")


@socketio.on("join")
def on_join(data):
    """Explicit join — used if client needs to re-join after reconnect."""
    if current_user.is_authenticated:
        join_room(f"user_{current_user.id}")
        if current_user.is_admin or current_user.is_super_admin:
            join_room("admins")
