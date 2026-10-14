import csv
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from uuid import UUID

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import business_required, role_required
from retail.models import RetailSupplier

from .forms import (
    BatchScheduleForm,
    ScheduledPaymentForm,
    SupplierBillForm,
    SupplierBillLineFormSet,
    SupplierPaymentForm,
    WholesalePromotionForm,
)
from .models import (
    ScheduledSupplierPayment,
    SupplierBill,
    SupplierPayment,
    WholesalePromotion,
)


def wholesale_only(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.user.business.business_type != "WHOLESALE":
            messages.error(request, "This page is only available to wholesale businesses.")
            return redirect("dashboard")
        return view(request, *args, **kwargs)
    return wrapped


manager_required = role_required(["OWNER", "MANAGER", "ADMIN", "SUPER_ADMIN"])


def _promotion_status(promotion, now=None):
    now = now or timezone.now()
    if promotion.status == "ACTIVE" and promotion.auto_expire and promotion.ends_at and promotion.ends_at < now:
        return "ENDED"
    if promotion.status in {"ACTIVE", "SCHEDULED"} and promotion.starts_at > now:
        return "SCHEDULED"
    if promotion.status == "SCHEDULED" and promotion.starts_at <= now:
        return "ACTIVE"
    return promotion.status


def _safe_csv_value(value):
    text = str(value or "")
    if text[:1] in {"=", "+", "-", "@"}:
        return "'" + text
    return text


@login_required
@business_required
@wholesale_only
def promotion_list_view(request):
    business = request.user.business
    promotions = WholesalePromotion.objects.filter(business=business).prefetch_related(
        "products", "redemptions",
    )
    search = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").upper()
    type_filter = request.GET.get("type", "").upper()
    tier_filter = request.GET.get("tier", "").strip()
    if search:
        promotions = promotions.filter(
            Q(name__icontains=search)
            | Q(products__name__icontains=search)
            | Q(customer_tiers__icontains=search)
        ).distinct()
    if type_filter in dict(WholesalePromotion.TYPES):
        promotions = promotions.filter(promotion_type=type_filter)
    if tier_filter:
        promotions = promotions.filter(customer_tiers__icontains=tier_filter)
    rows = [(promotion, _promotion_status(promotion)) for promotion in promotions]
    for promotion, _status in rows:
        promotion.tracked_revenue = sum(
            (redemption.revenue for redemption in promotion.redemptions.all()),
            Decimal("0"),
        )
    if status_filter in dict(WholesalePromotion.STATUSES):
        rows = [row for row in rows if row[1] == status_filter]

    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="wholesale-promotions.csv"'
        writer = csv.writer(response)
        writer.writerow(["Name", "Type", "Products", "Discount", "Customer tiers", "Starts", "Ends", "Revenue", "Status"])
        for promotion, status in rows:
            revenue = promotion.redemptions.aggregate(total=Sum("revenue"))["total"] or 0
            writer.writerow([
                _safe_csv_value(promotion.name),
                promotion.get_promotion_type_display(),
                _safe_csv_value(", ".join(promotion.products.values_list("name", flat=True))),
                f"{promotion.discount_percent or promotion.discount_amount or 0}",
                _safe_csv_value(promotion.customer_tiers or "All"),
                promotion.starts_at.isoformat(),
                promotion.ends_at.isoformat() if promotion.ends_at else "",
                revenue,
                promotion.get_status_display() if status == promotion.status else status.title(),
            ])
        return response

    now = timezone.now()
    period_start = now - timedelta(days=30)
    redemptions = WholesalePromotion.objects.filter(
        business=business,
        redemptions__redeemed_at__gte=period_start,
    ).annotate(
        promo_revenue=Sum("redemptions__revenue"),
        uses=Count("redemptions"),
    )
    promotion_revenue = sum((row.promo_revenue or Decimal("0") for row in redemptions), Decimal("0"))
    best_performer = redemptions.order_by("-promo_revenue").first()
    active_count = sum(
        _promotion_status(promotion) == "ACTIVE"
        for promotion in WholesalePromotion.objects.filter(business=business)
    )
    return render(request, "wholesale/promotions.html", {
        "rows": rows,
        "search": search,
        "status_filter": status_filter,
        "type_filter": type_filter,
        "tier_filter": tier_filter,
        "promotion_types": WholesalePromotion.TYPES,
        "promotion_statuses": WholesalePromotion.STATUSES,
        "total_count": len(rows),
        "active_count": active_count,
        "promotion_revenue": promotion_revenue,
        "average_uplift": Decimal("0"),
        "best_performer": best_performer,
    })


@login_required
@business_required
@wholesale_only
@manager_required
def promotion_create_view(request):
    form = WholesalePromotionForm(
        request.POST or None,
        business=request.user.business,
    )
    if request.method == "POST" and form.is_valid():
        promotion = form.save(commit=False)
        promotion.business = request.user.business
        promotion.created_by = request.user
        if promotion.starts_at > timezone.now():
            promotion.status = "SCHEDULED"
        elif request.POST.get("submit_action") == "activate":
            promotion.status = "ACTIVE"
        else:
            promotion.status = "DRAFT"
        promotion.save()
        form.save_m2m()
        messages.success(request, f"Promotion “{promotion.name}” saved.")
        return redirect("wholesale:promotion_detail", promotion_id=promotion.pk)
    return render(request, "wholesale/promotion_form.html", {
        "form": form,
        "page_title": "New promotion",
        "submit_label": "Save promotion",
    })


@login_required
@business_required
@wholesale_only
@manager_required
def promotion_edit_view(request, promotion_id):
    promotion = get_object_or_404(WholesalePromotion, business=request.user.business, pk=promotion_id)
    form = WholesalePromotionForm(
        request.POST or None,
        instance=promotion,
        business=request.user.business,
    )
    if request.method == "POST" and form.is_valid():
        updated = form.save(commit=False)
        if request.POST.get("submit_action") == "activate" and updated.status not in {"PAUSED", "ENDED"}:
            updated.status = "SCHEDULED" if updated.starts_at > timezone.now() else "ACTIVE"
        elif updated.status not in {"PAUSED", "ENDED", "DRAFT"}:
            updated.status = "SCHEDULED" if updated.starts_at > timezone.now() else "ACTIVE"
        updated.save()
        form.save_m2m()
        messages.success(request, f"Promotion “{updated.name}” updated.")
        return redirect("wholesale:promotion_detail", promotion_id=updated.pk)
    return render(request, "wholesale/promotion_form.html", {
        "form": form,
        "promotion": promotion,
        "page_title": "Edit promotion",
        "submit_label": "Save changes",
    })


@login_required
@business_required
@wholesale_only
def promotion_detail_view(request, promotion_id):
    promotion = get_object_or_404(
        WholesalePromotion.objects.prefetch_related("products", "redemptions"),
        business=request.user.business,
        pk=promotion_id,
    )
    redemptions = promotion.redemptions.select_related("sale").order_by("-redeemed_at")
    revenue = redemptions.aggregate(total=Sum("revenue"))["total"] or Decimal("0")
    quantity = redemptions.aggregate(total=Sum("eligible_quantity"))["total"] or 0
    products = list(promotion.products.all())
    sale_data = []
    if products:
        from sales.models import SaleItem

        period = promotion.ends_at or timezone.now()
        period_start = promotion.starts_at
        product_ids = [product.pk for product in products]
        for product in products:
            promo_sales = SaleItem.objects.filter(
                product=product,
                sale__business=request.user.business,
                sale__sale_date__gte=period_start,
                sale__sale_date__lte=period,
            ).aggregate(units=Sum("quantity"), revenue=Sum("total"))
            baseline_start = period_start - max(period - period_start, timedelta(days=1))
            baseline_end = period_start
            baseline = SaleItem.objects.filter(
                product=product,
                sale__business=request.user.business,
                sale__sale_date__gte=baseline_start,
                sale__sale_date__lt=baseline_end,
            ).aggregate(units=Sum("quantity"))["units"] or 0
            sale_data.append({
                "product": product,
                "promo_units": promo_sales["units"] or 0,
                "promo_revenue": promo_sales["revenue"] or Decimal("0"),
                "baseline_units": baseline,
            })
    return render(request, "wholesale/promotion_detail.html", {
        "promotion": promotion,
        "promotion_status": _promotion_status(promotion),
        "redemptions": redemptions,
        "revenue": revenue,
        "units_moved": quantity,
        "products": sale_data,
    })


@login_required
@business_required
@wholesale_only
@manager_required
@require_POST
def promotion_action_view(request, promotion_id):
    promotion = get_object_or_404(
        WholesalePromotion.objects.prefetch_related("products"),
        business=request.user.business,
        pk=promotion_id,
    )
    action = request.POST.get("action")
    if action == "pause" and _promotion_status(promotion) == "ACTIVE":
        promotion.status = "PAUSED"
        promotion.save(update_fields=["status", "updated_at"])
        messages.success(request, "Promotion paused.")
    elif action == "resume" and promotion.status == "PAUSED":
        promotion.status = "SCHEDULED" if promotion.starts_at > timezone.now() else "ACTIVE"
        promotion.save(update_fields=["status", "updated_at"])
        messages.success(request, "Promotion resumed.")
    elif action == "end" and promotion.status not in {"ENDED", "DRAFT"}:
        promotion.status = "ENDED"
        promotion.save(update_fields=["status", "updated_at"])
        messages.success(request, "Promotion ended.")
    elif action == "duplicate":
        clone = WholesalePromotion.objects.get(pk=promotion.pk)
        clone.pk = None
        clone.id = None
        clone.name = f"{promotion.name} (copy)"
        clone.status = "DRAFT"
        clone.created_by = request.user
        clone.save()
        clone.products.set(promotion.products.all())
        messages.success(request, "Draft copy created.")
        return redirect("wholesale:promotion_edit", promotion_id=clone.pk)
    elif action == "delete" and promotion.status == "DRAFT":
        promotion.delete()
        messages.success(request, "Draft promotion deleted.")
        return redirect("wholesale:promotions")
    else:
        messages.error(request, "That action is not available for this promotion.")
    return redirect("wholesale:promotion_detail", promotion_id=promotion.pk)


@login_required
@business_required
@wholesale_only
@manager_required
@require_POST
def promotion_bulk_action_view(request):
    ids = request.POST.getlist("promotion_ids")
    action = request.POST.get("action")
    promotions = WholesalePromotion.objects.filter(business=request.user.business, pk__in=ids)
    if not ids:
        messages.error(request, "Select at least one promotion.")
        return redirect("wholesale:promotions")
    if action == "pause":
        promotions.filter(status="ACTIVE").update(status="PAUSED", updated_at=timezone.now())
    elif action == "resume":
        for promotion in promotions.filter(status="PAUSED"):
            promotion.status = "SCHEDULED" if promotion.starts_at > timezone.now() else "ACTIVE"
            promotion.save(update_fields=["status", "updated_at"])
    elif action == "end":
        promotions.exclude(status__in=["ENDED", "DRAFT"]).update(
            status="ENDED", updated_at=timezone.now(),
        )
    else:
        messages.error(request, "Choose a valid bulk action.")
        return redirect("wholesale:promotions")
    messages.success(request, "Selected promotions updated.")
    return redirect("wholesale:promotions")


def _bill_queryset(business):
    return SupplierBill.objects.filter(business=business).select_related("supplier").prefetch_related(
        "payments", "scheduled_payments", "lines__product",
    )


def _bill_balance(bill):
    return max(bill.amount - (bill.amount_paid or Decimal("0")), Decimal("0"))


def _bill_days_due(bill, today):
    return (bill.due_date - today).days


@login_required
@business_required
@wholesale_only
def accounts_payable_view(request):
    business = request.user.business
    today = timezone.localdate()
    bills = list(_bill_queryset(business).exclude(status="VOID"))
    for bill in bills:
        bill.current_balance = _bill_balance(bill)
        bill.effective_status = (
            "PAID" if bill.current_balance <= 0
            else "DISPUTED" if bill.status == "DISPUTED"
            else "OVERDUE" if bill.days_until_due < 0
            else "DUE_SOON" if bill.days_until_due <= 3
            else "PARTIAL" if bill.current_balance < bill.amount
            else "ON_TIME"
        )

    search = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").upper()
    supplier_filter = request.GET.get("supplier", "")
    due_filter = request.GET.get("due", "").lower()
    overdue_only = request.GET.get("overdue") == "1"
    amount_min = request.GET.get("min", "").strip()
    amount_max = request.GET.get("max", "").strip()
    visible = bills
    filter_errors = []
    if search:
        visible = [
            bill for bill in visible
            if search.lower() in bill.supplier.name.lower()
            or search.lower() in bill.invoice_number.lower()
        ]
    if supplier_filter:
        try:
            supplier_id = UUID(supplier_filter)
        except ValueError:
            visible = []
            filter_errors.append("Choose a valid supplier.")
        else:
            visible = [bill for bill in visible if bill.supplier_id == supplier_id]
    if status_filter:
        visible = [bill for bill in visible if bill.effective_status == status_filter]
    if overdue_only:
        visible = [bill for bill in visible if bill.effective_status == "OVERDUE"]
    if due_filter == "week":
        visible = [bill for bill in visible if 0 <= bill.days_until_due <= 7]
    elif due_filter == "month":
        visible = [bill for bill in visible if 0 <= bill.days_until_due <= 30]
    amount_filtered = visible
    try:
        min_amount = Decimal(amount_min) if amount_min else None
        max_amount = Decimal(amount_max) if amount_max else None
        if (
            (min_amount is not None and (not min_amount.is_finite() or min_amount < 0))
            or (max_amount is not None and (not max_amount.is_finite() or max_amount < 0))
        ):
            raise InvalidOperation
        if min_amount is not None and max_amount is not None and min_amount > max_amount:
            raise InvalidOperation
    except InvalidOperation:
        filter_errors.append("Enter a valid non-negative amount range.")
        visible = amount_filtered
    else:
        if min_amount is not None:
            visible = [bill for bill in visible if bill.current_balance >= min_amount]
        if max_amount is not None:
            visible = [bill for bill in visible if bill.current_balance <= max_amount]

    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="accounts-payable.csv"'
        writer = csv.writer(response)
        writer.writerow(["Supplier", "Invoice", "Invoice date", "Due date", "Terms", "Amount", "Paid", "Balance", "Status"])
        for bill in visible:
            writer.writerow([
                _safe_csv_value(bill.supplier.name), _safe_csv_value(bill.invoice_number),
                bill.invoice_date, bill.due_date, bill.get_payment_terms_display(),
                bill.amount, bill.amount_paid, bill.current_balance, bill.effective_status,
            ])
        return response

    open_bills = [bill for bill in bills if bill.current_balance > 0]
    week_end = today + timedelta(days=7)
    overdue_bills = [bill for bill in open_bills if bill.days_until_due < 0]
    due_this_week = [bill for bill in open_bills if today <= bill.due_date <= week_end]
    aging = [
        ("Current", [bill for bill in open_bills if bill.days_until_due > 7]),
        ("Due this week", due_this_week),
        ("1–30 days overdue", [bill for bill in overdue_bills if 1 <= -bill.days_until_due <= 30]),
        ("31–60 days overdue", [bill for bill in overdue_bills if 31 <= -bill.days_until_due <= 60]),
        ("60+ days overdue", [bill for bill in overdue_bills if -bill.days_until_due > 60]),
    ]
    aging_rows = [
        {"label": label, "amount": sum((bill.current_balance for bill in subset), Decimal("0"))}
        for label, subset in aging
    ]
    aging_total = sum((row["amount"] for row in aging_rows), Decimal("0"))
    for row in aging_rows:
        row["percentage"] = (
            min(100, round(float(row["amount"] * 100 / aging_total)))
            if aging_total else 0
        )
    upcoming = []
    for week in range(6):
        start = today + timedelta(days=week * 7)
        end = start + timedelta(days=6)
        weekly_bills = [bill for bill in open_bills if start <= bill.due_date <= end]
        upcoming.append({
            "start": start,
            "end": end,
            "bills": weekly_bills,
            "total": sum((bill.current_balance for bill in weekly_bills), Decimal("0")),
        })

    supplier_summary = []
    suppliers = RetailSupplier.objects.filter(business=business).order_by("name")
    for supplier in suppliers:
        supplier_bills = [bill for bill in bills if bill.supplier_id == supplier.pk]
        supplier_open = [bill for bill in supplier_bills if bill.current_balance > 0]
        if not supplier_bills:
            continue
        supplier_summary.append({
            "supplier": supplier,
            "outstanding": sum((bill.current_balance for bill in supplier_open), Decimal("0")),
            "overdue": sum(
                (bill.current_balance for bill in supplier_open if bill.days_until_due < 0),
                Decimal("0"),
            ),
            "next_due": min(
                (bill.due_date for bill in supplier_open if bill.due_date >= today),
                default=None,
            ),
            "ytd_spent": sum(
                (bill.amount for bill in supplier_bills if bill.invoice_date.year == today.year),
                Decimal("0"),
            ),
        })
    scheduled_total = ScheduledSupplierPayment.objects.filter(
        business=business, status="SCHEDULED",
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    peak_week = max(upcoming, key=lambda week: week["total"], default=None)
    return render(request, "wholesale/accounts_payable.html", {
        "bills": visible,
        "search": search,
        "status_filter": status_filter,
        "supplier_filter": supplier_filter,
        "due_filter": due_filter,
        "overdue_only": overdue_only,
        "suppliers": suppliers,
        "total_ap": sum((bill.current_balance for bill in open_bills), Decimal("0")),
        "due_week_amount": sum((bill.current_balance for bill in due_this_week), Decimal("0")),
        "overdue_amount": sum((bill.current_balance for bill in overdue_bills), Decimal("0")),
        "overdue_supplier_count": len({bill.supplier_id for bill in overdue_bills}),
        "supplier_count": len(supplier_summary),
        "open_bill_count": len(open_bills),
        "aging_rows": aging_rows,
        "supplier_summary": supplier_summary,
        "upcoming": upcoming,
        "scheduled_total": scheduled_total,
        "peak_week": peak_week,
        "batch_form": BatchScheduleForm(business=business),
        "filter_error": " ".join(filter_errors),
    })


@login_required
@business_required
@wholesale_only
@manager_required
def supplier_bill_create_view(request):
    form = SupplierBillForm(request.POST or None, request.FILES or None, business=request.user.business)
    formset = SupplierBillLineFormSet(
        request.POST or None,
        prefix="lines",
        form_kwargs={"business": request.user.business},
    )
    form_valid = request.method == "POST" and form.is_valid()
    if form_valid:
        formset.instance.amount = form.cleaned_data["amount"]
    formset_valid = request.method == "POST" and formset.is_valid()
    if form_valid and formset_valid:
        try:
            with transaction.atomic():
                bill = form.save(commit=False)
                bill.business = request.user.business
                bill.created_by = request.user
                bill.save()
                formset.instance = bill
                lines = formset.save(commit=False)
                for line in lines:
                    line.bill = bill
                    line.save()
                for line in formset.deleted_objects:
                    line.delete()
        except IntegrityError:
            form.add_error("invoice_number", "This supplier already has a bill with that invoice number.")
        else:
            messages.success(request, f"Supplier bill {bill.invoice_number} recorded.")
            return redirect("wholesale:payables")
    return render(request, "wholesale/supplier_bill_form.html", {
        "form": form, "formset": formset, "line_form": formset.empty_form,
    })


@login_required
@business_required
@wholesale_only
def supplier_bill_detail_view(request, bill_id):
    bill = get_object_or_404(
        _bill_queryset(request.user.business),
        business=request.user.business,
        pk=bill_id,
    )
    balance = _bill_balance(bill)
    days_until_due = _bill_days_due(bill, timezone.localdate())
    active_scheduled_count = sum(
        schedule.status == "SCHEDULED" for schedule in bill.scheduled_payments.all()
    )
    payment_form = SupplierPaymentForm(initial={"amount": balance})
    schedule_form = ScheduledPaymentForm(initial={"amount": balance})
    return render(request, "wholesale/supplier_bill_detail.html", {
        "bill": bill,
        "balance": balance,
        "days_until_due": days_until_due,
        "effective_status": (
            "PAID" if balance <= 0 else "DISPUTED" if bill.status == "DISPUTED"
            else "OVERDUE" if days_until_due < 0
            else "DUE_SOON" if days_until_due <= 3 else "ON_TIME"
        ),
        "payment_form": payment_form,
        "schedule_form": schedule_form,
        "active_scheduled_count": active_scheduled_count,
    })


@login_required
@business_required
@wholesale_only
@manager_required
def supplier_bill_edit_view(request, bill_id):
    bill = get_object_or_404(SupplierBill, business=request.user.business, pk=bill_id)
    form = SupplierBillForm(
        request.POST or None, request.FILES or None, instance=bill, business=request.user.business,
    )
    if request.method == "POST" and form.is_valid():
        try:
            form.save()
        except IntegrityError:
            form.add_error("invoice_number", "This supplier already has a bill with that invoice number.")
        else:
            messages.success(request, f"Supplier bill {bill.invoice_number} updated.")
            return redirect("wholesale:bill_detail", bill_id=bill.pk)
    return render(request, "wholesale/supplier_bill_form.html", {"form": form, "bill": bill})


@login_required
@business_required
@wholesale_only
@manager_required
@require_POST
def supplier_bill_action_view(request, bill_id):
    bill = get_object_or_404(SupplierBill, business=request.user.business, pk=bill_id)
    action = request.POST.get("action")
    if bill.status == "VOID":
        messages.error(request, "Voided invoices cannot be changed.")
        return redirect("wholesale:bill_detail", bill_id=bill.pk)
    if bill.status == "DISPUTED" and action in {"payment", "schedule"}:
        messages.error(request, "Clear the dispute before scheduling or recording a payment.")
        return redirect("wholesale:bill_detail", bill_id=bill.pk)
    if action == "payment":
        form = SupplierPaymentForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                bill = SupplierBill.objects.select_for_update().get(pk=bill.pk)
                payment = form.save(commit=False)
                payment.business = bill.business
                payment.bill = bill
                payment.created_by = request.user
                scheduled_total = bill.scheduled_payments.filter(status="SCHEDULED").aggregate(
                    total=Sum("amount"),
                )["total"] or Decimal("0")
                if payment.amount + scheduled_total > _bill_balance(bill):
                    form.add_error(
                        "amount",
                        "Payment plus scheduled payments cannot exceed the outstanding balance. "
                        "Cancel or adjust a scheduled payment first.",
                    )
                else:
                    payment.save()
                    if _bill_balance(bill) <= 0:
                        bill.status = "PAID"
                    elif bill.status != "DISPUTED":
                        bill.status = "PARTIAL"
                    bill.save(update_fields=["status", "updated_at"])
                    messages.success(request, "Supplier payment recorded.")
                    return redirect("wholesale:bill_detail", bill_id=bill.pk)
        for error in form.errors.values():
            for message in error:
                messages.error(request, message)
    elif action == "schedule":
        form = ScheduledPaymentForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                bill = SupplierBill.objects.select_for_update().get(pk=bill.pk)
                scheduled_total = bill.scheduled_payments.filter(status="SCHEDULED").aggregate(
                    total=Sum("amount"),
                )["total"] or Decimal("0")
                schedule = form.save(commit=False)
                schedule.business = bill.business
                schedule.bill = bill
                schedule.created_by = request.user
                if schedule.amount + scheduled_total > _bill_balance(bill):
                    form.add_error(
                        "amount",
                        "Scheduled payments cannot exceed the outstanding balance.",
                    )
                else:
                    schedule.save()
                    messages.success(request, "Payment scheduled.")
                    return redirect("wholesale:bill_detail", bill_id=bill.pk)
        for error in form.errors.values():
            for message in error:
                messages.error(request, message)
    elif action == "dispute" and bill.status not in {"PAID", "VOID"}:
        with transaction.atomic():
            bill = SupplierBill.objects.select_for_update().get(pk=bill.pk)
            bill.status = "DISPUTED"
            bill.save(update_fields=["status", "updated_at"])
            bill.scheduled_payments.filter(status="SCHEDULED").update(status="CANCELLED")
        messages.success(request, "Bill marked as disputed and its pending payment schedules cancelled.")
    elif action == "clear_dispute" and bill.status == "DISPUTED":
        bill.status = (
            "PAID" if _bill_balance(bill) <= 0
            else "PARTIAL" if _bill_balance(bill) < bill.amount
            else "OPEN"
        )
        bill.save(update_fields=["status", "updated_at"])
        messages.success(request, "Dispute status cleared.")
    elif action == "cancel_schedule":
        schedule = get_object_or_404(
            ScheduledSupplierPayment,
            business=request.user.business,
            bill=bill,
            pk=request.POST.get("schedule_id"),
            status="SCHEDULED",
        )
        schedule.status = "CANCELLED"
        schedule.save(update_fields=["status"])
        messages.success(request, "Scheduled payment cancelled.")
    else:
        messages.error(request, "This action is not available for the bill.")
    return redirect("wholesale:bill_detail", bill_id=bill.pk)


@login_required
@business_required
@wholesale_only
@manager_required
@require_POST
def batch_schedule_payments_view(request):
    form = BatchScheduleForm(request.POST, business=request.user.business)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect("wholesale:payables")
    scheduled_count = 0
    with transaction.atomic():
        for bill in form.cleaned_data["bills"].select_for_update().order_by("pk"):
            balance = _bill_balance(bill)
            scheduled_total = bill.scheduled_payments.filter(status="SCHEDULED").aggregate(
                total=Sum("amount"),
            )["total"] or Decimal("0")
            available_balance = balance - scheduled_total
            if available_balance <= 0:
                continue
            ScheduledSupplierPayment.objects.create(
                business=request.user.business,
                bill=bill,
                amount=available_balance,
                scheduled_date=form.cleaned_data["scheduled_date"],
                payment_method=form.cleaned_data["payment_method"],
                created_by=request.user,
            )
            scheduled_count += 1
    messages.success(request, f"Scheduled payments for {scheduled_count} bill(s).")
    return redirect("wholesale:payables")
