from django.urls import path

from . import pages, views

app_name = "barber"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("goals/", pages.goals, name="goals"),
    path("goals/live/", pages.live_goals, name="live_goals"),
    path("goals/<uuid:goal_id>/delete/", pages.delete_goal, name="delete_goal"),
    path("money/", pages.money, name="money"),
    path("money/live/", pages.live_money, name="live_money"),
    path("schedule/", pages.schedule, name="schedule"),
    path("schedule/live/", pages.live_schedule, name="live_schedule"),
    path("schedule/<uuid:shift_id>/delete/", pages.delete_shift, name="delete_shift"),
    path("clients/", pages.clients, name="clients"),
    path("clients/live/", pages.live_clients, name="live_clients"),
    path("clients/<uuid:customer_id>/", pages.client_detail, name="client_detail"),
    path("board/", views.board, name="board"),
    path("barbers/", views.barbers, name="barbers"),
    path("services/", views.services, name="services"),
    path("api/live-floor/", views.live_floor, name="live_floor"),
    path("api/live-board/", views.live_board, name="live_board"),
    path("appointments/create/", views.create_board_appointment, name="create_appointment"),
    path("appointments/<uuid:appointment_id>/chairs/<uuid:chair_id>/seat/", views.seat_appointment, name="seat_appointment"),
    path("chairs/<uuid:chair_id>/seat-next/", views.seat_next, name="seat_next"),
    path("appointments/<uuid:appointment_id>/finish/", views.finish_appointment, name="finish_appointment"),
]
