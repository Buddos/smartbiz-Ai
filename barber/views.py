from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date, parse_datetime
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import business_required, role_required
from accounts.models import User
from analytics.models import BusinessInsight
from sales.models import Sale

from .models import Appointment, BarberService, Chair


def _chair_queryset(request):
    chairs = Chair.objects.filter(business=request.user.business, is_active=True).select_related("barber")
    return chairs.filter(barber=request.user) if request.user.role == "BARBER" else chairs


def _floor_data(request):
    """Return only persisted shop-floor data; this is also used by the live endpoint."""
    business = request.user.business
    today = timezone.localdate()
    now = timezone.now()
    chairs = _chair_queryset(request)
    current = Appointment.objects.filter(
        business=business, chair__in=chairs, status="IN_CHAIR"
    ).select_related("customer", "service", "barber", "chair")
    by_chair = {appointment.chair_id: appointment for appointment in current}
    chair_rows = []
    for chair in chairs:
        appointment = by_chair.get(chair.id)
        chair_rows.append({
            "id": str(chair.id), "label": chair.label, "status": "busy" if appointment else chair.status.lower(),
            "barber": chair.barber.get_full_name() if chair.barber else "Unassigned",
            "client": appointment.display_client_name if appointment else None,
            "service": appointment.service.name if appointment else None,
            "started_at": appointment.started_at.isoformat() if appointment and appointment.started_at else None,
            "appointment_id": str(appointment.id) if appointment else None,
        })
    queue = Appointment.objects.filter(
        business=business, status__in=["WAITING", "CONFIRMED", "BOOKED"], start_time__date__lte=today
    ).select_related("service", "barber", "customer").order_by("-priority", "checked_in_at", "start_time")
    if request.user.role == "BARBER":
        queue = queue.filter(barber=request.user)
    queue_count = queue.count()
    queue_rows = [{
        "id": str(item.id), "name": item.display_client_name,
        "phone": item.client_phone or (item.customer.phone if item.customer_id else ""),
        "service": item.service.name,
        "barber": item.barber.get_full_name() if item.barber else "Any barber",
        "wait": max(0, int((now - (item.checked_in_at or item.start_time)).total_seconds() // 60)),
        "priority": item.priority,
    } for item in queue[:12]]
    sales = Sale.objects.filter(business=business, sale_date__date=today)
    if request.user.role == "BARBER":
        sales = sales.filter(barber=request.user)
    revenue = sales.aggregate(total=Sum("total"))["total"] or 0
    completed = Appointment.objects.filter(business=business, completed_at__date=today, status="DONE")
    if request.user.role == "BARBER":
        completed = completed.filter(barber=request.user)
    waiting_now = queue.filter(status="WAITING")
    wait_values = [
        max(0, int((now - (checked_in_at or start_time)).total_seconds() // 60))
        for checked_in_at, start_time in waiting_now.values_list("checked_in_at", "start_time")
    ]
    return {"chairs": chair_rows, "queue": queue_rows, "metrics": {
        "revenue": float(revenue), "cuts": completed.count(), "waiting": queue_count,
        "occupied": sum(1 for row in chair_rows if row["status"] == "busy"), "chairs": len(chair_rows),
        "average_wait": round(sum(wait_values) / len(wait_values)) if wait_values else 0,
        "longest_wait": max(wait_values, default=0),
    }}


@login_required
@business_required
@role_required(["OWNER", "MANAGER", "BARBER", "ADMIN", "SUPER_ADMIN"])
def dashboard(request):
    data = _floor_data(request)
    insights = BusinessInsight.objects.filter(business=request.user.business, is_dismissed=False).order_by("-generated_at")[:2]
    return render(request, "barber/workspace.html", {"page": "dashboard", "floor": data, "insights": insights})


@login_required
@business_required
@role_required(["OWNER", "MANAGER", "BARBER", "ADMIN", "SUPER_ADMIN"])
def board(request):
    selected_date = parse_date(request.GET.get("date", "")) or timezone.localdate()
    return render(request, "barber/workspace.html", {
        "page": "board",
        "board_date": selected_date.isoformat(),
        "floor": _floor_data(request),
        "board_data": _board_data(request, selected_date),
        "services": BarberService.objects.filter(business=request.user.business, is_active=True),
        "chairs": _chair_queryset(request),
        "barbers": User.objects.filter(
            business=request.user.business, role="BARBER", is_active=True
        ).order_by("first_name", "last_name"),
    })


@login_required
@business_required
@role_required(["OWNER", "MANAGER", "ADMIN", "SUPER_ADMIN"])
def barbers(request):
    staff = User.objects.filter(
        business=request.user.business, role="BARBER", is_active=True
    ).order_by("first_name", "last_name")
    # Keep these aggregates separate: joining appointments and sales would multiply
    # totals for a barber with more than one row in either table.
    today = timezone.localdate()
    for barber in staff:
        barber.appointments_today = Appointment.objects.filter(barber=barber, start_time__date=today).count()
        barber.revenue_today = Sale.objects.filter(barber=barber, sale_date__date=today).aggregate(total=Sum("total"))["total"] or 0
    return render(request, "barber/workspace.html", {"page": "barbers", "barbers": staff})


@login_required
@business_required
@role_required(["OWNER", "MANAGER", "BARBER", "ADMIN", "SUPER_ADMIN"])
def services(request):
    business = request.user.business
    if request.method == "POST":
        if request.user.role == "BARBER":
            messages.error(request, "Only an owner or manager can change the service catalogue.")
            return redirect("barber:services")
        service_id = request.POST.get("service_id")
        service = get_object_or_404(BarberService, id=service_id, business=business) if service_id else BarberService(business=business)
        service.name = request.POST.get("name", "").strip()
        service.category = request.POST.get("category", "CUT")
        service.price = request.POST.get("price") or 0
        service.duration_min = request.POST.get("duration_min") or 30
        service.is_active = request.POST.get("is_active") == "on"
        if service.name:
            service.save()
            messages.success(request, "Service saved.")
        else:
            messages.error(request, "A service name is required.")
        return redirect("barber:services")
    return render(request, "barber/workspace.html", {
        "page": "services", "services": BarberService.objects.filter(business=business).prefetch_related("barbers"),
        "service_categories": BarberService.CATEGORY_CHOICES,
    })


@login_required
@business_required
@role_required(["OWNER", "MANAGER", "BARBER", "ADMIN", "SUPER_ADMIN"])
def live_floor(request):
    return JsonResponse(_floor_data(request))


def _board_data(request, selected_date):
    business = request.user.business
    appointments = Appointment.objects.filter(
        business=business,
        start_time__date=selected_date,
    ).select_related("chair", "barber", "service", "customer", "sale").order_by("start_time")
    if request.user.role == "BARBER":
        appointments = appointments.filter(barber=request.user)

    appointment_rows = [{
        "id": str(item.id),
        "client": item.display_client_name,
        "phone": item.client_phone or (item.customer.phone if item.customer_id else ""),
        "service": item.service.name,
        "price": float(item.service.price),
        "duration": item.duration_min,
        "status": item.status,
        "status_label": item.get_status_display(),
        "start_time": timezone.localtime(item.start_time).isoformat(),
        "started_at": timezone.localtime(item.started_at).isoformat() if item.started_at else None,
        "chair_id": str(item.chair_id) if item.chair_id else "",
        "chair": item.chair.label if item.chair_id else "Unassigned",
        "barber": item.barber.get_full_name() if item.barber else "Unassigned",
        "barber_id": str(item.barber_id) if item.barber_id else "",
        "notes": item.notes,
        "appointment_id": str(item.id),
    } for item in appointments]

    floor = _floor_data(request)
    completed = Appointment.objects.filter(
        business=business,
        completed_at__date=selected_date,
        status="DONE",
    )
    if request.user.role == "BARBER":
        completed = completed.filter(barber=request.user)
    floor["metrics"].update({
        "done": completed.count(),
    })
    return {
        "date": selected_date.isoformat(),
        "chairs": floor["chairs"],
        "appointments": appointment_rows,
        "queue": floor["queue"],
        "metrics": floor["metrics"],
    }


@login_required
@business_required
@role_required(["OWNER", "MANAGER", "BARBER", "ADMIN", "SUPER_ADMIN"])
def live_board(request):
    selected_date = parse_date(request.GET.get("date", "")) or timezone.localdate()
    return JsonResponse(_board_data(request, selected_date))


@require_POST
@login_required
@business_required
@role_required(["OWNER", "MANAGER", "BARBER", "ADMIN", "SUPER_ADMIN"])
def create_board_appointment(request):
    business = request.user.business
    service = get_object_or_404(
        BarberService,
        id=request.POST.get("service_id"),
        business=business,
        is_active=True,
    )
    appointment_type = request.POST.get("appointment_type", "booking")
    if appointment_type not in {"booking", "walk_in"}:
        return JsonResponse({"error": "Choose a booking or walk-in."}, status=400)

    name = request.POST.get("client_name", "").strip()
    phone = request.POST.get("client_phone", "").strip()
    if not name:
        return JsonResponse({"error": "Enter the client's name."}, status=400)

    barber_id = request.POST.get("barber_id") or None
    if request.user.role == "BARBER":
        barber_id = str(request.user.id)
    barber = None
    if barber_id:
        barber = get_object_or_404(
            User,
            id=barber_id,
            business=business,
            role="BARBER",
            is_active=True,
        )

    chair_id = request.POST.get("chair_id") or None
    chair = get_object_or_404(_chair_queryset(request), id=chair_id) if chair_id else None
    if request.user.role == "BARBER" and chair and chair.barber_id not in {None, request.user.id}:
        return JsonResponse({"error": "You can only assign appointments to your own chair."}, status=403)
    if chair and not barber:
        barber = chair.barber
    if barber and not service.barbers.filter(id=barber.id).exists() and service.barbers.exists():
        return JsonResponse({"error": "This barber is not assigned to the selected service."}, status=400)

    start_time = timezone.now()
    if appointment_type == "booking":
        submitted_start = parse_datetime(request.POST.get("start_time", ""))
        if not submitted_start:
            return JsonResponse({"error": "Choose a valid booking date and time."}, status=400)
        start_time = timezone.make_aware(submitted_start) if timezone.is_naive(submitted_start) else submitted_start

    status = "WAITING" if appointment_type == "walk_in" else "BOOKED"
    appointment = Appointment.objects.create(
        business=business,
        client_name=name,
        client_phone=phone,
        service=service,
        barber=barber,
        chair=chair,
        start_time=start_time,
        duration_min=service.duration_min,
        status=status,
        source="WALK_IN" if appointment_type == "walk_in" else "BOOKING",
        checked_in_at=timezone.now() if appointment_type == "walk_in" else None,
    )
    return JsonResponse({"success": True, "appointment_id": str(appointment.id)})


@require_POST
@login_required
@business_required
@role_required(["OWNER", "MANAGER", "BARBER", "ADMIN", "SUPER_ADMIN"])
def seat_appointment(request, appointment_id, chair_id):
    with transaction.atomic():
        chair = get_object_or_404(_chair_queryset(request).select_for_update(), id=chair_id)
        appointment = get_object_or_404(
            Appointment.objects.select_for_update(),
            id=appointment_id,
            business=request.user.business,
            status__in=["WAITING", "CONFIRMED", "BOOKED"],
            start_time__date__lte=timezone.localdate(),
        )
        if request.user.role == "BARBER" and appointment.barber_id not in {None, request.user.id}:
            return JsonResponse({"error": "You can only seat your own clients."}, status=403)
        if chair.barber_id and appointment.barber_id and chair.barber_id != appointment.barber_id:
            return JsonResponse({"error": "This appointment is assigned to another barber."}, status=409)
        if Appointment.objects.filter(chair=chair, status="IN_CHAIR").exclude(id=appointment_id).exists():
            return JsonResponse({"error": "That chair is already occupied."}, status=409)
        appointment.chair = chair
        appointment.barber = chair.barber or appointment.barber or request.user
        appointment.status = "IN_CHAIR"
        appointment.started_at = timezone.now()
        if not appointment.checked_in_at:
            appointment.checked_in_at = appointment.started_at
        appointment.save(update_fields=[
            "chair", "barber", "status", "started_at", "checked_in_at", "updated_at",
        ])
    return JsonResponse(_floor_data(request))


@require_POST
@login_required
@business_required
@role_required(["OWNER", "MANAGER", "BARBER", "ADMIN", "SUPER_ADMIN"])
def seat_next(request, chair_id):
    chair = get_object_or_404(_chair_queryset(request), id=chair_id)
    appointments = Appointment.objects.filter(
        business=request.user.business, status__in=["WAITING", "CONFIRMED", "BOOKED"], start_time__date__lte=timezone.localdate()
    )
    if request.user.role == "BARBER":
        appointments = appointments.filter(barber=request.user)
    appointment = appointments.order_by("-priority", "checked_in_at", "start_time").first()
    if not appointment:
        return JsonResponse({"error": "There is nobody waiting."}, status=409)
    appointment.chair = chair
    appointment.barber = chair.barber or request.user
    appointment.status, appointment.started_at = "IN_CHAIR", timezone.now()
    appointment.save(update_fields=["chair", "barber", "status", "started_at", "updated_at"])
    chair.status = "IDLE"
    chair.save(update_fields=["status", "updated_at"])
    return JsonResponse(_floor_data(request))


@require_POST
@login_required
@business_required
@role_required(["OWNER", "MANAGER", "BARBER", "ADMIN", "SUPER_ADMIN"])
def finish_appointment(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id, business=request.user.business)
    if request.user.role == "BARBER" and appointment.barber_id != request.user.id:
        return JsonResponse({"error": "You can only finish your own appointments."}, status=403)
    appointment.status, appointment.completed_at = "DONE", timezone.now()
    appointment.save(update_fields=["status", "completed_at", "updated_at"])
    return JsonResponse(_floor_data(request))
