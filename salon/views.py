from datetime import timedelta
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_http_methods

from accounts.decorators import business_required, role_required
from accounts.models import User, UserActivity
from customers.forms import CustomerForm
from customers.models import Customer
from products.models import Product
from sales.models import Sale

from .forms import (
    SalonAppointmentForm,
    SalonClientPackageForm,
    SalonPackageRedemptionForm,
    SalonServiceForm,
)
from .models import SalonAppointment, SalonClientPackage, SalonPackageRedemption


def _salon_required(view_func):
    @login_required
    @business_required
    @role_required(["OWNER", "MANAGER", "STAFF", "ADMIN", "SUPER_ADMIN"])
    def wrapped(request, *args, **kwargs):
        if request.user.business.business_type != "SALON":
            messages.error(request, "This page is only available to salon businesses.")
            return redirect("dashboard")
        return view_func(request, *args, **kwargs)

    return wrapped


@_salon_required
@require_http_methods(["GET", "POST"])
def appointments(request):
    business = request.user.business
    if request.method == "POST" and request.POST.get("action") == "status":
        appointment = get_object_or_404(
            SalonAppointment, id=request.POST.get("appointment_id"), business=business
        )
        status = request.POST.get("status")
        valid_statuses = {choice[0] for choice in SalonAppointment.STATUS_CHOICES}
        if status not in valid_statuses:
            messages.error(request, "Choose a valid appointment status.")
        elif status == "COMPLETED" and appointment.status != "COMPLETED":
            messages.error(request, "Appointments are completed through checkout so the sale stays linked.")
        elif appointment.status == "COMPLETED" and status != "COMPLETED":
            messages.error(request, "A completed appointment cannot be changed.")
        else:
            appointment.status = status
            appointment.save(update_fields=["status", "updated_at"])
            messages.success(request, f"Appointment updated to {appointment.get_status_display().lower()}.")
        return redirect(f"{reverse('salon:appointments')}?date={appointment.starts_at.date().isoformat()}")

    if request.method == "POST":
        form = SalonAppointmentForm(request.POST, business=business)
        if form.is_valid():
            appointment = form.save(commit=False)
            appointment.business = business
            appointment.client_name = form.cleaned_data.get("client_name", "").strip()
            appointment.client_phone = form.cleaned_data.get("client_phone", "").strip()
            appointment.duration_min = sum(
                int(service.metadata.get("duration_min", 30))
                for service in form.cleaned_data["services"]
            )
            appointment.save()
            appointment.services.set(form.cleaned_data["services"])
            UserActivity.objects.create(
                user=request.user,
                action="CREATE",
                model_name="SalonAppointment",
                object_id=str(appointment.id),
                changes={"client": appointment.display_client_name, "status": appointment.status},
                business=business,
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
            messages.success(request, f"Appointment booked for {appointment.display_client_name}.")
            return redirect(f"{reverse('salon:appointments')}?date={appointment.starts_at.date().isoformat()}")
    else:
        form = SalonAppointmentForm(business=business)

    selected_date = parse_date(request.GET.get("date", "")) or timezone.localdate()
    appointments_for_day = SalonAppointment.objects.filter(
        business=business,
        starts_at__date=selected_date,
    ).select_related("customer", "stylist").prefetch_related("services")
    search = request.GET.get("search", "").strip()
    if search:
        appointments_for_day = appointments_for_day.filter(
            Q(client_name__icontains=search)
            | Q(client_phone__icontains=search)
            | Q(customer__name__icontains=search)
            | Q(services__name__icontains=search)
            | Q(stylist__first_name__icontains=search)
            | Q(stylist__last_name__icontains=search)
        ).distinct()
    status_filter = request.GET.get("status", "").strip()
    if status_filter in {value for value, _ in SalonAppointment.STATUS_CHOICES}:
        appointments_for_day = appointments_for_day.filter(status=status_filter)
    day_appointments = SalonAppointment.objects.filter(
        business=business, starts_at__date=selected_date
    )
    context = {
        "page": "appointments",
        "form": form,
        "appointments": appointments_for_day,
        "selected_date": selected_date,
        "previous_date": selected_date - timedelta(days=1),
        "next_date": selected_date + timedelta(days=1),
        "search": search,
        "status_filter": status_filter,
        "status_choices": SalonAppointment.STATUS_CHOICES,
        "booked_count": day_appointments.exclude(status__in=["CANCELLED", "NO_SHOW"]).count(),
        "completed_count": day_appointments.filter(status="COMPLETED").count(),
        "waiting_count": day_appointments.filter(status="CHECKED_IN").count(),
        "stylist_count": day_appointments.values("stylist_id").distinct().exclude(stylist_id=None).count(),
    }
    return render(request, "salon/appointments.html", context)


@_salon_required
@require_http_methods(["GET", "POST"])
def bookings_pipeline(request):
    business = request.user.business
    if request.method == "POST":
        target_status = request.POST.get("status", "")
        allowed_statuses = {
            "BOOKED", "CONFIRMED", "CHECKED_IN", "IN_SERVICE", "NO_SHOW", "CANCELLED",
        }
        if target_status not in allowed_statuses:
            messages.error(request, "Choose a valid booking stage.")
        else:
            with transaction.atomic():
                appointment = get_object_or_404(
                    SalonAppointment.objects.select_for_update(),
                    id=request.POST.get("appointment_id"),
                    business=business,
                )
                if appointment.status == "COMPLETED":
                    messages.error(request, "Completed appointments can only be changed through their recorded sale.")
                else:
                    appointment.status = target_status
                    appointment.save(update_fields=["status", "updated_at"])
                    messages.success(
                        request,
                        f"{appointment.display_client_name} moved to {appointment.get_status_display().lower()}.",
                    )
        if target_status not in allowed_statuses:
            selected_date = parse_date(request.POST.get("date", "")) or timezone.localdate()
            return redirect(f"{reverse('salon:bookings_pipeline')}?date={selected_date.isoformat()}")
        return redirect(f"{reverse('salon:bookings_pipeline')}?date={appointment.starts_at.date().isoformat()}")

    selected_date = parse_date(request.GET.get("date", "")) or timezone.localdate()
    appointments_for_day = SalonAppointment.objects.filter(
        business=business,
        starts_at__date=selected_date,
    ).select_related("customer", "stylist").prefetch_related("services")
    search = request.GET.get("search", "").strip()
    if search:
        appointments_for_day = appointments_for_day.filter(
            Q(client_name__icontains=search)
            | Q(client_phone__icontains=search)
            | Q(customer__name__icontains=search)
            | Q(services__name__icontains=search)
            | Q(stylist__first_name__icontains=search)
            | Q(stylist__last_name__icontains=search)
        ).distinct()
    active_stages = [
        ("BOOKED", "Requested"),
        ("CONFIRMED", "Confirmed"),
        ("CHECKED_IN", "Checked in"),
        ("IN_SERVICE", "In service"),
    ]
    open_count = appointments_for_day.filter(
        status__in=[status for status, _ in active_stages]
    ).count()
    filtered_appointments = appointments_for_day
    pipeline_columns = [
        {
            "status": status,
            "label": label,
            "appointments": filtered_appointments.filter(status=status),
        }
        for status, label in active_stages
    ]
    return render(request, "salon/bookings_pipeline.html", {
        "page": "pipeline",
        "selected_date": selected_date,
        "previous_date": selected_date - timedelta(days=1),
        "next_date": selected_date + timedelta(days=1),
        "search": search,
        "columns": pipeline_columns,
        "appointments": filtered_appointments,
        "open_count": open_count,
        "completed_count": appointments_for_day.filter(status="COMPLETED").count(),
        "closed_count": appointments_for_day.filter(status__in=["NO_SHOW", "CANCELLED"]).count(),
    })


@_salon_required
def stylists(request):
    business = request.user.business
    search = request.GET.get("search", "").strip()
    staff = User.objects.filter(
        business=business,
        role__in=["STAFF", "MANAGER"],
        is_active=True,
    ).order_by("first_name", "last_name")
    if search:
        staff = staff.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(email__icontains=search)
            | Q(phone_number__icontains=search)
        )

    today = timezone.localdate()
    month_start = today.replace(day=1)
    for stylist in staff:
        stylist.appointments_today = SalonAppointment.objects.filter(
            business=business, stylist=stylist, starts_at__date=today
        ).count()
        stylist.services_done_today = SalonAppointment.objects.filter(
            business=business,
            stylist=stylist,
            starts_at__date=today,
            status="COMPLETED",
        ).count()
        stylist.revenue_today = Sale.objects.filter(
            business=business,
            sale_date__date=today,
            metadata__served_by__id=str(stylist.id),
        ).aggregate(total=Sum("total"))["total"] or 0
        stylist.revenue_month = Sale.objects.filter(
            business=business,
            sale_date__date__gte=month_start,
            metadata__served_by__id=str(stylist.id),
        ).aggregate(total=Sum("total"))["total"] or 0

    day_appointments = SalonAppointment.objects.filter(business=business, starts_at__date=today)
    day_sales = Sale.objects.filter(business=business, sale_date__date=today)
    return render(request, "salon/stylists.html", {
        "page": "stylists",
        "stylists": staff,
        "search": search,
        "staff_count": staff.count(),
        "appointments_today": day_appointments.exclude(status__in=["CANCELLED", "NO_SHOW"]).count(),
        "completed_today": day_appointments.filter(status="COMPLETED").count(),
        "sales_today": day_sales.filter(metadata__served_by__id__isnull=False).count(),
    })


@_salon_required
@require_http_methods(["GET", "POST"])
def client_packages(request):
    business = request.user.business
    package_form = SalonClientPackageForm(business=business)
    redemption_form = SalonPackageRedemptionForm(business=business)
    if request.method == "POST" and request.POST.get("action") == "redeem":
        redemption_form = SalonPackageRedemptionForm(request.POST, business=business)
        if redemption_form.is_valid():
            package_id = redemption_form.cleaned_data["client_package"].id
            with transaction.atomic():
                package = get_object_or_404(
                    SalonClientPackage.objects.select_for_update().select_related("customer"),
                    id=package_id,
                    business=business,
                )
                service_id = redemption_form.cleaned_data["service"].id
                appointment = redemption_form.cleaned_data["appointment"]
                if not package.is_usable:
                    redemption_form.add_error(
                        "client_package",
                        "This package has no usable sessions or has expired.",
                    )
                else:
                    service = Product.objects.select_for_update().filter(
                        id=service_id,
                        business=business,
                        is_active=True,
                        metadata__salon_service=True,
                    ).first()
                    if service is None or not package.services.filter(
                        id=service_id,
                        business=business,
                    ).exists():
                        redemption_form.add_error("service", "Choose an active service included in this package.")
                if not redemption_form.errors and appointment:
                    appointment = SalonAppointment.objects.select_for_update().filter(
                        id=appointment.id,
                        business=business,
                    ).first()
                    if appointment is None or appointment.status not in {"CHECKED_IN", "IN_SERVICE"}:
                        redemption_form.add_error("appointment", "The linked appointment is no longer active.")
                if not redemption_form.errors and appointment and package.customer_id != appointment.customer_id:
                    redemption_form.add_error("appointment", "The appointment client does not match this package.")
                if not redemption_form.errors and appointment and not appointment.services.filter(
                    id=service_id,
                ).exists():
                    redemption_form.add_error("appointment", "The service is not included in this appointment.")
                if not redemption_form.errors and appointment and SalonPackageRedemption.objects.filter(
                    client_package=package,
                    appointment=appointment,
                ).exists():
                    redemption_form.add_error("appointment", "This package was already redeemed for the appointment.")
                if not redemption_form.errors:
                    redemption = SalonPackageRedemption.objects.create(
                        business=business,
                        client_package=package,
                        service=service,
                        appointment=appointment,
                        redeemed_by=request.user,
                        notes=redemption_form.cleaned_data["notes"],
                    )
                    SalonClientPackage.objects.filter(id=package.id).update(
                        sessions_redeemed=F("sessions_redeemed") + 1,
                        updated_at=timezone.now(),
                    )
                    package.refresh_from_db(fields=["sessions_redeemed"])
                    UserActivity.objects.create(
                        user=request.user,
                        action="UPDATE",
                        model_name="SalonClientPackage",
                        object_id=str(package.id),
                        changes={
                            "redemption_id": str(redemption.id),
                            "service": service.name,
                            "sessions_remaining": package.sessions_remaining,
                        },
                        business=business,
                        ip_address=request.META.get("REMOTE_ADDR"),
                        user_agent=request.META.get("HTTP_USER_AGENT", ""),
                    )
                    messages.success(request, f"One {service.name} session redeemed for {package.customer.name}.")
                    return redirect("salon:client_packages")
    elif request.method == "POST":
        package_form = SalonClientPackageForm(request.POST, business=business)
        if package_form.is_valid():
            package = package_form.save(commit=False)
            package.business = business
            package.created_by = request.user
            package.save()
            package_form.save_m2m()
            UserActivity.objects.create(
                user=request.user,
                action="CREATE",
                model_name="SalonClientPackage",
                object_id=str(package.id),
                changes={
                    "client": package.customer.name,
                    "name": package.name,
                    "sessions": package.sessions_total,
                },
                business=business,
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
            messages.success(request, f"{package.name} was added to {package.customer.name}'s package tracker.")
            return redirect("salon:client_packages")

    packages = SalonClientPackage.objects.filter(
        business=business,
    ).select_related("customer", "purchase_sale").prefetch_related("services")
    search = request.GET.get("search", "").strip()
    if search:
        packages = packages.filter(
            Q(customer__name__icontains=search)
            | Q(customer__phone__icontains=search)
            | Q(name__icontains=search)
            | Q(services__name__icontains=search)
        ).distinct()
    today = timezone.localdate()
    usable_packages = SalonClientPackage.objects.filter(
        business=business,
        sessions_redeemed__lt=F("sessions_total"),
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gte=today))
    redemption_history = SalonPackageRedemption.objects.filter(
        business=business,
    ).select_related("client_package__customer", "service", "redeemed_by", "appointment")[:30]
    redeemable_packages = redemption_form.fields["client_package"].queryset.prefetch_related("services")
    package_service_map = {
        str(package.id): [
            str(service.id)
            for service in package.services.all()
            if service.business_id == business.id
            and service.is_active
            and service.metadata.get("salon_service")
        ]
        for package in redeemable_packages
    }
    return render(request, "salon/client_packages.html", {
        "page": "client_packages",
        "package_form": package_form,
        "redemption_form": redemption_form,
        "packages": packages,
        "search": search,
        "package_count": packages.count(),
        "usable_count": usable_packages.count(),
        "exhausted_count": SalonClientPackage.objects.filter(
            business=business,
            sessions_redeemed__gte=F("sessions_total"),
        ).count(),
        "redemptions_today": SalonPackageRedemption.objects.filter(
            business=business,
            redeemed_at__date=today,
        ).count(),
        "redemption_history": redemption_history,
        "package_service_map": package_service_map,
    })


@_salon_required
@require_http_methods(["GET", "POST"])
def services(request):
    business = request.user.business
    if request.method == "POST":
        service_id = request.POST.get("service_id", "").strip()
        if service_id == "deactivate":
            product = get_object_or_404(
                Product,
                id=request.POST.get("product_id"),
                business=business,
                metadata__salon_service=True,
            )
            product.is_active = False
            product.save(update_fields=["is_active", "updated_at"])
            messages.success(request, f"{product.name} was removed from the active service menu.")
            return redirect("salon:services")

        form = SalonServiceForm(request.POST, business=business)
        if form.is_valid():
            product = Product.objects.create(
                business=business,
                name=form.cleaned_data["name"],
                sku=f"SVC-{uuid4().hex[:12].upper()}",
                purchase_price=0,
                selling_price=form.cleaned_data["price"],
                current_stock=0,
                is_active=True,
                created_by=request.user,
                description=form.cleaned_data["description"],
                metadata={
                    "salon_service": True,
                    "duration_min": form.cleaned_data["duration_min"],
                },
            )
            UserActivity.objects.create(
                user=request.user,
                action="CREATE",
                model_name="SalonService",
                object_id=str(product.id),
                changes={"name": product.name, "price": str(product.selling_price)},
                business=business,
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
            messages.success(request, f"{product.name} was added to the service menu.")
            return redirect("salon:services")
    else:
        form = SalonServiceForm(business=business)

    services_qs = Product.objects.filter(
        business=business,
        metadata__salon_service=True,
    ).order_by("name")
    return render(request, "salon/services.html", {
        "page": "services",
        "form": form,
        "services": services_qs,
        "active_count": services_qs.filter(is_active=True).count(),
        "package_count": SalonClientPackage.objects.filter(business=business).count(),
    })


@_salon_required
@require_http_methods(["GET", "POST"])
def clients(request):
    business = request.user.business
    if request.method == "POST":
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save(commit=False)
            customer.business = business
            customer.save()
            UserActivity.objects.create(
                user=request.user,
                action="CREATE",
                model_name="Customer",
                object_id=str(customer.id),
                changes={"name": customer.name},
                business=business,
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
            messages.success(request, f"{customer.name} was added to your client list.")
            return redirect("salon:clients")
    else:
        form = CustomerForm()

    customer_qs = Customer.objects.filter(business=business, is_active=True).annotate(
        visit_count=Count("sales", distinct=True),
        lifetime_spend=Sum("sales__total"),
        last_visit=Max("sales__sale_date"),
    )
    search = request.GET.get("search", "").strip()
    if search:
        customer_qs = customer_qs.filter(
            Q(name__icontains=search) | Q(phone__icontains=search) | Q(email__icontains=search)
        )
    segment = request.GET.get("segment", "")
    if segment == "vip":
        customer_qs = customer_qs.filter(lifetime_spend__gte=50000)
    elif segment == "new":
        customer_qs = customer_qs.filter(created_at__date__gte=timezone.localdate() - timedelta(days=30))

    paginator = Paginator(customer_qs.order_by("-last_visit", "name"), 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    all_clients = Customer.objects.filter(business=business, is_active=True)
    vip_clients = all_clients.annotate(lifetime_spend=Sum("sales__total")).filter(
        lifetime_spend__gte=50000
    )
    month_start = timezone.localdate().replace(day=1)
    return render(request, "salon/clients.html", {
        "page": "clients",
        "form": form,
        "page_obj": page_obj,
        "search": search,
        "segment": segment,
        "client_count": all_clients.count(),
        "new_client_count": all_clients.filter(created_at__date__gte=timezone.localdate() - timedelta(days=30)).count(),
        "vip_count": vip_clients.count(),
        "active_sale_client_count": Sale.objects.filter(
            business=business, sale_date__date__gte=month_start, customer__isnull=False
        ).values("customer_id").distinct().count(),
    })
