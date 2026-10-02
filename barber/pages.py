from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import calendar
import math

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Max, Q, Sum
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from accounts.decorators import business_required, role_required
from analytics.models import BusinessInsight
from customers.models import Customer
from expenses.models import Expense
from sales.models import Sale, SaleItem

from .forms import BarberGoalForm, BarberShiftForm
from .models import Appointment, BarberGoal, BarberShift, Chair


BARBER_ROLES = ["OWNER", "MANAGER", "BARBER", "ADMIN", "SUPER_ADMIN"]
MANAGER_ROLES = ["OWNER", "MANAGER", "ADMIN", "SUPER_ADMIN"]
FINANCE_ROLES = MANAGER_ROLES + ["ACCOUNTANT"]


def _money(value):
    return float(value or 0)


def _client_rows(business, search="", status="", barber=None):
    today = timezone.localdate()
    customers = Customer.objects.filter(business=business, is_active=True).order_by("name")
    if barber:
        customers = customers.filter(
            Q(sales__barber=barber) | Q(barber_appointments__barber=barber)
        ).distinct()

    sales = Sale.objects.filter(business=business, customer__isnull=False)
    completed_visits = Appointment.objects.filter(
        business=business, customer__isnull=False, status="DONE"
    )
    if barber:
        sales = sales.filter(barber=barber)
        completed_visits = completed_visits.filter(barber=barber)
    spends = {
        row["customer_id"]: row
        for row in sales
        .exclude(order_status="CANCELLED")
        .values("customer_id")
        .annotate(spend=Sum("total"), sales_count=Count("id"), sale_last=Max("sale_date"))
    }
    visits = {
        row["customer_id"]: row
        for row in completed_visits.values("customer_id").annotate(
            visit_count=Count("id"), visit_last=Max("completed_at")
        )
    }
    preferred_barber = defaultdict(Counter)
    barber_names = {}
    appointments = completed_visits.filter(barber__isnull=False).values_list(
        "customer_id", "barber_id", "barber__first_name", "barber__last_name"
    )
    for customer_id, barber_id, first_name, last_name in appointments:
        preferred_barber[customer_id][barber_id] += 1
        barber_names[barber_id] = f"{first_name} {last_name}".strip()

    lifetime_spends = sorted(row["spend"] or Decimal("0") for row in spends.values())
    vip_threshold = lifetime_spends[math.floor((len(lifetime_spends) - 1) * 0.9)] if lifetime_spends else None
    rows = []
    for customer in customers:
        sale = spends.get(customer.id, {})
        appointment = visits.get(customer.id, {})
        last_visit = max(
            (value for value in (sale.get("sale_last"), appointment.get("visit_last")) if value),
            default=None,
        )
        days_since = (today - timezone.localtime(last_visit).date()).days if last_visit else None
        visit_count = appointment.get("visit_count", 0) or sale.get("sales_count", 0)
        spend = sale.get("spend") or Decimal("0")
        if vip_threshold is not None and spend >= vip_threshold and spend > 0:
            client_status = "vip"
        elif customer.created_at.date() >= today - timedelta(days=30) and not visit_count:
            client_status = "new"
        elif days_since is None or days_since >= 45:
            client_status = "at-risk"
        elif days_since >= 30:
            client_status = "due"
        else:
            client_status = "regular"
        favorite_id = preferred_barber[customer.id].most_common(1)
        rows.append({
            "id": str(customer.id),
            "name": customer.name,
            "phone": customer.phone,
            "email": customer.email,
            "status": client_status,
            "last_visit": timezone.localtime(last_visit).strftime("%d %b %Y") if last_visit else "No visits yet",
            "days_since": days_since,
            "visits": visit_count,
            "spent": _money(spend),
            "barber": barber_names.get(favorite_id[0][0], "—") if favorite_id else "—",
            "url": reverse("barber:client_detail", kwargs={"customer_id": customer.id}),
        })

    summary = Counter(row["status"] for row in rows)
    visible_rows = [
        row for row in rows
        if (not status or row["status"] == status)
        and (
            not search
            or search.casefold() in f'{row["name"]} {row["phone"]} {row["email"]}'.casefold()
        )
    ]
    return visible_rows, {
        "total": len(rows),
        "regular": summary["regular"],
        "due": summary["due"],
        "at_risk": summary["at-risk"],
        "vip": summary["vip"],
    }


def _client_payload(request):
    rows, summary = _client_rows(
        request.user.business,
        search=request.GET.get("search", "").strip(),
        status=request.GET.get("status", "").strip(),
        barber=request.user if request.user.role == "BARBER" else None,
    )
    return {"clients": rows, "summary": summary}


@login_required
@business_required
@role_required(BARBER_ROLES)
def clients(request):
    payload = _client_payload(request)
    return render(request, "barber/clients.html", {
        "page": "clients",
        "clients": payload["clients"],
        "summary": payload["summary"],
        "search": request.GET.get("search", ""),
        "status": request.GET.get("status", ""),
    })


@login_required
@business_required
@role_required(BARBER_ROLES)
@never_cache
def live_clients(request):
    return JsonResponse(_client_payload(request))


@login_required
@business_required
@role_required(BARBER_ROLES)
def client_detail(request, customer_id):
    business = request.user.business
    customers = Customer.objects.filter(business=business, is_active=True)
    if request.user.role == "BARBER":
        customers = customers.filter(
            Q(sales__barber=request.user) | Q(barber_appointments__barber=request.user)
        ).distinct()
    customer = get_object_or_404(customers, id=customer_id)
    sale_queryset = customer.sales.filter(business=business).exclude(order_status="CANCELLED")
    completed_visits = customer.barber_appointments.filter(
        business=business, status="DONE"
    )
    if request.user.role == "BARBER":
        sale_queryset = sale_queryset.filter(barber=request.user)
        completed_visits = completed_visits.filter(barber=request.user)
    spend = sale_queryset.aggregate(total=Sum("total"))["total"] or Decimal("0")
    sale_count = sale_queryset.count()
    sales = sale_queryset.order_by("-sale_date")[:50]
    completed_visits = completed_visits.select_related("service", "barber").order_by("-completed_at")
    visit_total = completed_visits.count()
    appointments = completed_visits[:50]
    appointments_by_sale = {item.sale_id: item for item in appointments if item.sale_id}
    barber_counts = Counter(
        completed_visits.filter(barber__isnull=False)
        .values_list("barber__first_name", "barber__last_name")
    )
    preferred_barber = "—"
    if barber_counts:
        first, last = barber_counts.most_common(1)[0][0]
        preferred_barber = f"{first} {last}".strip()
    timeline = []
    for sale in sales:
        appointment = appointments_by_sale.get(sale.id)
        timeline.append({
            "date": sale.sale_date,
            "service": appointment.service.name if appointment else "Sale",
            "barber": appointment.barber.get_full_name() if appointment and appointment.barber else "—",
            "amount": sale.total,
        })
    for appointment in appointments:
        if not appointment.sale_id:
            timeline.append({
                "date": appointment.completed_at or appointment.start_time,
                "service": appointment.service.name,
                "barber": appointment.barber.get_full_name() if appointment.barber else "—",
                "amount": appointment.service.price,
            })
    timeline.sort(key=lambda row: row["date"], reverse=True)
    visit_dates = sorted({
        timezone.localtime(item["date"]).date()
        for item in timeline
    })
    gaps = [(right - left).days for left, right in zip(visit_dates, visit_dates[1:])]
    average_gap = round(sum(gaps) / len(gaps)) if gaps else None
    average_spend = (spend / max(1, sale_count)).quantize(Decimal("0.01"))
    overdue = average_gap and visit_dates and (timezone.localdate() - visit_dates[-1]).days > average_gap
    most_booked = completed_visits.values("service__name").annotate(
        count=Count("id")
    ).order_by("-count").first()
    most_booked_service = most_booked["service__name"] if most_booked else "—"
    most_booked_share = round(most_booked["count"] / visit_total * 100) if most_booked and visit_total else 0
    weekday = completed_visits.values("start_time__week_day").annotate(
        count=Count("id")
    ).order_by("-count").first()
    hour = completed_visits.values("start_time__hour").annotate(
        count=Count("id")
    ).order_by("-count").first()
    weekday_names = {1: "Sunday", 2: "Monday", 3: "Tuesday", 4: "Wednesday", 5: "Thursday", 6: "Friday", 7: "Saturday"}
    favorite_time = "—"
    if weekday and hour:
        hour_value = hour["start_time__hour"]
        favorite_time = f'{weekday_names[weekday["start_time__week_day"]]} around {hour_value % 12 or 12} {"AM" if hour_value < 12 else "PM"}'
    return render(request, "barber/client_detail.html", {
        "page": "clients",
        "customer": customer,
        "timeline": timeline[:50],
        "spend": spend,
        "visit_count": visit_total or sale_count,
        "average_gap": average_gap,
        "average_spend": average_spend,
        "preferred_barber": preferred_barber,
        "most_booked_service": most_booked_service,
        "most_booked_share": most_booked_share,
        "favorite_time": favorite_time,
        "overdue_days": (
            (timezone.localdate() - visit_dates[-1]).days - average_gap
            if overdue else 0
        ),
    })


def _goal_value(goal, business, today, barber=None):
    start = today
    end = today
    if goal.metric == "WEEKLY_CUTS":
        start = today - timedelta(days=today.weekday())
        end = today
        appointments = Appointment.objects.filter(
            business=business, status="DONE", completed_at__date__range=(start, end)
        )
        if barber:
            appointments = appointments.filter(barber=barber)
        value = appointments.count()
    elif goal.metric == "MONTHLY_CLIENTS":
        start = today.replace(day=1)
        end = today
        clients = Customer.objects.filter(business=business, created_at__date__range=(start, end))
        if barber:
            clients = clients.filter(barber_appointments__barber=barber)
        value = clients.distinct().count()
    elif goal.metric == "MONTHLY_REVENUE":
        start = today.replace(day=1)
        end = today
        sales = Sale.objects.filter(
            business=business, sale_date__date__range=(start, end)
        ).exclude(order_status="CANCELLED")
        if barber:
            sales = sales.filter(barber=barber)
        value = sales.aggregate(total=Sum("total"))["total"] or Decimal("0")
    elif goal.metric == "MONTHLY_ATTACH_RATE":
        start = today.replace(day=1)
        end = today
        completed = Appointment.objects.filter(
            business=business, status="DONE", completed_at__date__range=(start, end)
        ).select_related("service", "sale").prefetch_related("sale__sale_items")
        if barber:
            completed = completed.filter(barber=barber)
        total_visits = completed.count()
        attached = sum(
            1 for appointment in completed
            if appointment.sale_id and any(
                item.product_name.casefold() != appointment.service.name.casefold()
                for item in appointment.sale.sale_items.all()
            )
        )
        value = Decimal(attached * 100 / total_visits) if total_visits else Decimal("0")
    elif goal.metric == "MONTHLY_REPEAT_RATE":
        start = today.replace(day=1)
        end = today
        completed = Appointment.objects.filter(
            business=business,
            status="DONE",
            completed_at__date__range=(start, end),
            customer__isnull=False,
        )
        if barber:
            completed = completed.filter(barber=barber)
        customer_counts = completed.values("customer_id").annotate(visits=Count("id"))
        served = customer_counts.count()
        repeated = customer_counts.filter(visits__gte=2).count()
        value = Decimal(repeated * 100 / served) if served else Decimal("0")
    else:
        sales = Sale.objects.filter(
            business=business, sale_date__date=today
        ).exclude(order_status="CANCELLED")
        if barber:
            sales = sales.filter(barber=barber)
        value = sales.aggregate(total=Sum("total"))["total"] or Decimal("0")
    return Decimal(str(value))


def _goal_rows(business, barber=None):
    today = timezone.localdate()
    rows = []
    for goal in BarberGoal.objects.filter(business=business, is_active=True):
        current = _goal_value(goal, business, today, barber)
        ratio = current / goal.target if goal.target else Decimal("0")
        rows.append({
            "id": str(goal.id),
            "metric": goal.get_metric_display(),
            "unit": "KSh " if goal.metric in {"DAILY_REVENUE", "MONTHLY_REVENUE"} else (
                "%" if goal.metric in {"MONTHLY_ATTACH_RATE", "MONTHLY_REPEAT_RATE"} else ""
            ),
            "current": _money(current),
            "target": _money(goal.target),
            "percent": min(100, round(float(ratio * 100))),
            "remaining": _money(max(Decimal("0"), goal.target - current)),
            "hit": current >= goal.target,
        })
    return rows


def _goal_payload(business, barber=None):
    rows = _goal_rows(business, barber)
    today = timezone.localdate()
    daily_goal = next(
        (goal for goal in BarberGoal.objects.filter(business=business, is_active=True)
         if goal.metric == "DAILY_REVENUE"),
        None,
    )
    streak = 0
    if daily_goal:
        daily_totals = {
            row["sale_date__date"]: row["total"]
            for row in Sale.objects.filter(
                business=business,
                sale_date__date__gte=today - timedelta(days=365),
                **({"barber": barber} if barber else {}),
            )
            .exclude(order_status="CANCELLED")
            .values("sale_date__date")
            .annotate(total=Sum("total"))
        }
        first_day = 0 if daily_totals.get(today, Decimal("0")) >= daily_goal.target else 1
        for offset in range(first_day, 366):
            day = today - timedelta(days=offset)
            total = daily_totals.get(day, Decimal("0"))
            if total >= daily_goal.target:
                streak += 1
            else:
                break
    return {"goals": rows, "daily_streak": streak}


@login_required
@business_required
@role_required(BARBER_ROLES)
def goals(request):
    business = request.user.business
    if request.method == "POST":
        if request.user.role not in MANAGER_ROLES:
            messages.error(request, "Only an owner or manager can add goals.")
            return redirect("barber:goals")
        form = BarberGoalForm(request.POST)
        if form.is_valid():
            goal = form.save(commit=False)
            goal.business = business
            goal.save()
            messages.success(request, "Goal added.")
            return redirect("barber:goals")
    else:
        form = BarberGoalForm()
    barber = request.user if request.user.role == "BARBER" else None
    payload = _goal_payload(business, barber)
    coach_insight = BusinessInsight.objects.filter(
        business=business,
        is_dismissed=False,
        insight_type__in=["FORECAST", "OPPORTUNITY", "RECOMMENDATION"],
    ).order_by("-generated_at").first()
    if barber:
        coach_insight = None
    return render(request, "barber/goals.html", {
        "page": "goals",
        "form": form,
        "goals": payload["goals"],
        "daily_streak": payload["daily_streak"],
        "coach_insight": coach_insight,
        "can_manage": request.user.role in MANAGER_ROLES,
    })


@login_required
@business_required
@role_required(BARBER_ROLES)
@never_cache
def live_goals(request):
    barber = request.user if request.user.role == "BARBER" else None
    return JsonResponse(_goal_payload(request.user.business, barber))


@login_required
@business_required
@role_required(MANAGER_ROLES)
@require_POST
def delete_goal(request, goal_id):
    get_object_or_404(BarberGoal, id=goal_id, business=request.user.business).delete()
    messages.success(request, "Goal removed.")
    return redirect("barber:goals")


def _shift_payload(request, week_start):
    business = request.user.business
    dates = [week_start + timedelta(days=offset) for offset in range(7)]
    chairs = Chair.objects.filter(business=business, is_active=True).order_by("label")
    shifts = BarberShift.objects.filter(
        business=business, shift_date__range=(dates[0], dates[-1])
    ).select_related("barber", "chair")
    if request.user.role == "BARBER":
        shifts = shifts.filter(barber=request.user)
        chairs = chairs.filter(
            Q(barber=request.user)
            | Q(scheduled_shifts__barber=request.user, scheduled_shifts__shift_date__range=(dates[0], dates[-1]))
        ).distinct()
    shifts = list(shifts)
    rows = [{
        "id": str(item.id),
        "date": item.shift_date.isoformat(),
        "chair_id": str(item.chair_id),
        "chair": item.chair.label,
        "barber": item.barber.get_full_name(),
        "start": item.start_time.strftime("%H:%M"),
        "end": item.end_time.strftime("%H:%M"),
        "day_off": item.is_day_off,
    } for item in shifts]
    shift_minutes = Counter()
    for item in shifts:
        if not item.is_day_off:
            shift_minutes[item.chair_id] += (
                item.end_time.hour * 60 + item.end_time.minute
                - item.start_time.hour * 60 - item.start_time.minute
            )
    appointments = Appointment.objects.filter(
        business=business,
        chair__in=chairs,
        start_time__date__range=(dates[0], dates[-1]),
    ).exclude(status__in=["CANCELLED", "NO_SHOW"]).select_related("chair")
    if request.user.role == "BARBER":
        appointments = appointments.filter(barber=request.user)
    booked_minutes = Counter()
    for shift in shifts:
        if shift.is_day_off:
            continue
        shift_start = timezone.make_aware(datetime.combine(shift.shift_date, shift.start_time))
        shift_end = timezone.make_aware(datetime.combine(shift.shift_date, shift.end_time))
        for appointment in appointments:
            if appointment.chair_id != shift.chair_id:
                continue
            appointment_start = timezone.localtime(appointment.start_time)
            appointment_end = appointment_start + timedelta(minutes=appointment.duration_min)
            overlap_start = max(shift_start, appointment_start)
            overlap_end = min(shift_end, appointment_end)
            if overlap_end > overlap_start:
                booked_minutes[shift.chair_id] += int((overlap_end - overlap_start).total_seconds() // 60)
    utilization = [{
        "chair": chair.label,
        "percent": min(100, round(booked_minutes.get(chair.id, 0) / total * 100)) if total else 0,
        "booked_hours": round(booked_minutes.get(chair.id, 0) / 60, 1),
        "scheduled_hours": round(total / 60, 1),
    } for chair in chairs for total in [shift_minutes.get(chair.id, 0)]]
    today = timezone.localdate()
    today_shifts = [item for item in shifts if item.shift_date == today and not item.is_day_off]
    today_appointments = Appointment.objects.filter(
        business=business, start_time__date=today
    ).exclude(status__in=["CANCELLED", "NO_SHOW"])
    if request.user.role == "BARBER":
        today_appointments = today_appointments.filter(barber=request.user)
    historical_walkins = Appointment.objects.filter(
        business=business,
        source="WALK_IN",
        start_time__date__gte=today - timedelta(days=56),
        start_time__date__lt=today,
    )
    if request.user.role == "BARBER":
        historical_walkins = historical_walkins.filter(barber=request.user)
    weekday_counts = list(historical_walkins.values("start_time__week_day").annotate(count=Count("id")))
    weekday_avg = {
        row["start_time__week_day"]: round(row["count"] / 8, 1)
        for row in weekday_counts
    }
    today_walkin_avg = weekday_avg.get(today.isoweekday() % 7 + 1, 0)
    opening = min((item.start_time for item in today_shifts), default=None)
    closing = max((item.end_time for item in today_shifts), default=None)
    return {
        "days": [{"date": day.isoformat(), "label": day.strftime("%a %d")} for day in dates],
        "chairs": [{"id": str(chair.id), "label": chair.label} for chair in chairs],
        "shifts": rows,
        "utilization": utilization,
        "snapshot": {
            "staffed_chairs": len({item.chair_id for item in today_shifts}),
            "opening": opening.strftime("%H:%M") if opening else "—",
            "closing": closing.strftime("%H:%M") if closing else "—",
            "booked": today_appointments.count(),
            "walkins_average": today_walkin_avg,
        },
    }


@login_required
@business_required
@role_required(BARBER_ROLES)
def schedule(request):
    business = request.user.business
    selected = timezone.localdate()
    if request.GET.get("week"):
        selected = parse_date(request.GET["week"])
        if selected is None:
            return HttpResponseBadRequest("Provide a valid week date.")
    week_start = selected - timedelta(days=selected.weekday())
    if request.method == "POST":
        if request.user.role not in MANAGER_ROLES:
            messages.error(request, "Only an owner or manager can change the schedule.")
            return redirect("barber:schedule")
        form = BarberShiftForm(request.POST, business=business)
        if form.is_valid():
            shift = form.save(commit=False)
            shift.business = business
            shift.save()
            messages.success(request, "Shift saved.")
            return redirect(f"{request.path}?week={shift.shift_date.isoformat()}")
    else:
        form = BarberShiftForm(
            business=business,
            initial={"shift_date": selected, "start_time": time(9, 0), "end_time": time(18, 0)},
        )
    data = _shift_payload(request, week_start)
    return render(request, "barber/schedule.html", {
        "page": "schedule",
        "week_start": week_start,
        "week_end": week_start + timedelta(days=6),
        "schedule_data": data,
        "form": form,
        "can_manage": request.user.role in MANAGER_ROLES,
        "previous_week": (week_start - timedelta(days=7)).isoformat(),
        "next_week": (week_start + timedelta(days=7)).isoformat(),
    })


@login_required
@business_required
@role_required(BARBER_ROLES)
@never_cache
def live_schedule(request):
    try:
        selected = date.fromisoformat(request.GET.get("week", ""))
    except ValueError:
        return HttpResponseBadRequest("Provide a valid week date.")
    week_start = selected - timedelta(days=selected.weekday())
    return JsonResponse(_shift_payload(request, week_start))


@login_required
@business_required
@role_required(MANAGER_ROLES)
@require_POST
def delete_shift(request, shift_id):
    shift = get_object_or_404(BarberShift, id=shift_id, business=request.user.business)
    week = shift.shift_date.isoformat()
    shift.delete()
    messages.success(request, "Shift removed.")
    return redirect(f"{reverse('barber:schedule')}?week={week}")


def _period_dates(request):
    today = timezone.localdate()
    period = request.GET.get("period", "month")
    if period == "today":
        return period, today, today, today - timedelta(days=1), today - timedelta(days=1)
    if period == "week":
        start = today - timedelta(days=today.weekday())
        return period, start, today, start - timedelta(days=7), start - timedelta(days=1)
    if period == "custom":
        start = parse_date(request.GET.get("start", ""))
        end = parse_date(request.GET.get("end", ""))
        if start is None or end is None:
            raise ValueError("Choose a valid start and end date.")
        if end < start:
            raise ValueError("End date must be on or after the start date.")
        span = (end - start).days + 1
        return period, start, end, start - timedelta(days=span), start - timedelta(days=1)
    start = today.replace(day=1)
    prior_end = start - timedelta(days=1)
    prior_start = prior_end.replace(day=1)
    comparable_end = prior_start + timedelta(days=min(today.day, calendar.monthrange(prior_start.year, prior_start.month)[1]) - 1)
    return "month", start, today, prior_start, comparable_end


def _money_payload(request):
    period, start, end, previous_start, previous_end = _period_dates(request)
    business = request.user.business
    sales = Sale.objects.filter(
        business=business, sale_date__date__range=(start, end)
    ).exclude(order_status="CANCELLED")
    previous_sales = Sale.objects.filter(
        business=business, sale_date__date__range=(previous_start, previous_end)
    ).exclude(order_status="CANCELLED")
    expenses = Expense.objects.filter(business=business, expense_date__range=(start, end))
    previous_expenses = Expense.objects.filter(
        business=business, expense_date__range=(previous_start, previous_end)
    )
    revenue = sales.aggregate(total=Sum("total"))["total"] or Decimal("0")
    product_cost = SaleItem.objects.filter(
        sale__business=business,
        sale__sale_date__date__range=(start, end),
    ).exclude(sale__order_status="CANCELLED").aggregate(
        total=Sum(F("quantity") * F("cost_price"))
    )["total"] or Decimal("0")
    expense_total = expenses.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    prior_revenue = previous_sales.aggregate(total=Sum("total"))["total"] or Decimal("0")
    prior_expenses = previous_expenses.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    service_rows = Appointment.objects.filter(
        business=business, sale__isnull=False, sale__sale_date__date__range=(start, end)
    ).values_list("sale_id", "service__name")
    service_by_sale = {}
    for sale_id, service_name in service_rows:
        service_by_sale.setdefault(sale_id, service_name.casefold())
    tips = sales.aggregate(total=Sum("tip"))["total"] or Decimal("0")
    services = sum(
        (
            item_total or Decimal("0")
            for sale_id, product_name, item_total in SaleItem.objects.filter(
                sale__business=business,
                sale__sale_date__date__range=(start, end),
            ).exclude(sale__order_status="CANCELLED").values_list("sale_id", "product_name", "total")
            if service_by_sale.get(sale_id) == product_name.casefold()
        ),
        Decimal("0"),
    )
    product_revenue = max(Decimal("0"), revenue - services - tips)
    expense_breakdown = list(expenses.values("category__name").annotate(total=Sum("amount")).order_by("-total"))
    prior_by_category = {
        row["category__name"] or "Uncategorised": row["total"]
        for row in previous_expenses.values("category__name").annotate(total=Sum("amount"))
    }
    expense_alerts = []
    for row in expense_breakdown:
        name = row["category__name"] or "Uncategorised"
        prior = prior_by_category.get(name, Decimal("0"))
        current = row["total"] or Decimal("0")
        if prior > 0 and current > prior * Decimal("1.15"):
            expense_alerts.append({
                "name": name,
                "amount": _money(current - prior),
                "percent": round(float((current - prior) / prior * 100)),
            })
    days = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
    if len(days) > 31:
        days = days[-31:]
    sale_by_day = {
        row["sale_date__date"]: row["total"]
        for row in sales.values("sale_date__date").annotate(total=Sum("total"))
    }
    expense_by_day = {
        row["expense_date"]: row["total"]
        for row in expenses.values("expense_date").annotate(total=Sum("amount"))
    }
    last_days = [timezone.localdate() - timedelta(days=offset) for offset in range(6, -1, -1)]
    daily_cash = []
    for day in last_days:
        incoming = Sale.objects.filter(
            business=business, sale_date__date=day, payment_method__in=["CASH", "M-PESA"]
        ).exclude(order_status="CANCELLED").aggregate(total=Sum("amount_paid"))["total"] or Decimal("0")
        outgoing = Expense.objects.filter(business=business, expense_date=day).aggregate(total=Sum("amount"))["total"] or Decimal("0")
        daily_cash.append({"date": day.strftime("%a %d"), "in": _money(incoming), "out": _money(outgoing), "net": _money(incoming - outgoing)})
    cash_in = sales.filter(payment_method__in=["CASH", "M-PESA"]).aggregate(total=Sum("amount_paid"))["total"] or Decimal("0")
    profit = revenue - expense_total - product_cost
    margin = (profit / revenue * 100) if revenue else Decimal("0")
    change = ((revenue - prior_revenue) / prior_revenue * 100) if prior_revenue else None
    trend_rows = [
        {"date": day.strftime("%d %b"), "revenue": _money(sale_by_day.get(day, 0)), "expenses": _money(expense_by_day.get(day, 0))}
        for day in days
    ]
    peak = max((max(row["revenue"], row["expenses"]) for row in trend_rows), default=0) or 1
    for row in trend_rows:
        row["revenue_width"] = round(row["revenue"] / peak * 100)
        row["expense_width"] = round(row["expenses"] / peak * 100)
    return {
        "period": period,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "revenue": _money(revenue),
        "expenses": _money(expense_total),
        "profit": _money(profit),
        "product_cost": _money(product_cost),
        "cash_in": _money(cash_in),
        "cash_out": _money(expense_total),
        "margin": round(float(margin), 1),
        "revenue_change": round(float(change), 1) if change is not None else None,
        "expense_change": round(float((expense_total - prior_expenses) / prior_expenses * 100), 1) if prior_expenses else None,
        "sources": [
            {"name": "Services", "amount": _money(services), "percent": round(float(services / revenue * 100)) if revenue else 0},
            {"name": "Retail products", "amount": _money(product_revenue), "percent": round(float(product_revenue / revenue * 100)) if revenue else 0},
            {"name": "Tips", "amount": _money(tips), "percent": round(float(tips / revenue * 100)) if revenue else 0},
        ],
        "expense_breakdown": [
            {"name": row["category__name"] or "Uncategorised", "amount": _money(row["total"])}
            for row in expense_breakdown
        ],
        "expense_alerts": expense_alerts,
        "trend": trend_rows,
        "cash_days": daily_cash,
    }


@login_required
@business_required
@role_required(FINANCE_ROLES)
def money(request):
    try:
        data = _money_payload(request)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))
    return render(request, "barber/money.html", {"page": "money", "money": data})


@login_required
@business_required
@role_required(FINANCE_ROLES)
@never_cache
def live_money(request):
    try:
        return JsonResponse(_money_payload(request))
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))
