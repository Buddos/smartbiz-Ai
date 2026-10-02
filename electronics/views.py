from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import business_required
from analytics.models import BusinessInsight
from expenses.models import Expense
from inventory.models import InventoryTransaction
from products.models import Product
from sales.models import Sale, SaleItem

from .forms import CreditPlanForm, PurchaseOrderForm, RepairJobForm, SupplierForm
from .models import CreditPlan, PurchaseOrder, PurchaseOrderItem, RepairJob, Supplier


def _electronics_business(request):
    business = request.user.business
    if business.business_type != "ELECTRONICS":
        messages.error(request, "This workspace is only available to electronics businesses.")
        return None
    return business


@login_required
@business_required
def supplier_list_view(request):
    business = _electronics_business(request)
    if business is None:
        return redirect("dashboard")

    supplier_form = SupplierForm(prefix="supplier")
    order_form = PurchaseOrderForm(prefix="order", business=business)
    if request.method == "POST" and request.POST.get("form_type") == "supplier":
        supplier_form = SupplierForm(request.POST, prefix="supplier")
        if supplier_form.is_valid():
            supplier = supplier_form.save(commit=False)
            supplier.business = business
            supplier.save()
            messages.success(request, f"Supplier {supplier.name} added.")
            return redirect("electronics:suppliers")
    elif request.method == "POST" and request.POST.get("form_type") == "order":
        order_form = PurchaseOrderForm(request.POST, prefix="order", business=business)
        if order_form.is_valid():
            with transaction.atomic():
                order = PurchaseOrder.objects.create(
                    business=business,
                    supplier=order_form.cleaned_data["supplier"],
                    expected_date=order_form.cleaned_data["expected_date"],
                    notes=order_form.cleaned_data["notes"],
                    created_by=request.user,
                )
                PurchaseOrderItem.objects.create(
                    order=order,
                    product=order_form.cleaned_data["product"],
                    quantity=order_form.cleaned_data["quantity"],
                    unit_cost=order_form.cleaned_data["unit_cost"],
                )
                order.total = order.items.aggregate(total=Sum(F("quantity") * F("unit_cost")))["total"] or 0
                order.save(update_fields=["total"])
            messages.success(request, f"Purchase order {order.order_number} created.")
            return redirect("electronics:suppliers")

    suppliers = Supplier.objects.filter(business=business, is_active=True).annotate(
        product_count=Count("purchase_orders__items__product", distinct=True),
        outstanding_orders=Count(
            "purchase_orders",
            filter=Q(purchase_orders__status__in=["DRAFT", "SENT", "PARTIAL"]),
            distinct=True,
        ),
    )
    orders = PurchaseOrder.objects.filter(business=business).select_related("supplier").prefetch_related(
        "items__product"
    )[:20]
    return render(request, "electronics/suppliers.html", {
        "supplier_form": supplier_form,
        "order_form": order_form,
        "suppliers": suppliers,
        "orders": orders,
        "supplier_count": suppliers.count(),
        "purchase_order_count": PurchaseOrder.objects.filter(business=business).count(),
        "open_order_count": PurchaseOrder.objects.filter(
            business=business, status__in=["DRAFT", "SENT", "PARTIAL"]
        ).count(),
        "page": "suppliers",
    })


@login_required
@business_required
@require_POST
def purchase_order_receive_view(request, order_id):
    business = _electronics_business(request)
    if business is None:
        return redirect("dashboard")
    with transaction.atomic():
        order = get_object_or_404(
            PurchaseOrder.objects.select_for_update().prefetch_related("items__product"),
            id=order_id,
            business=business,
        )
        if order.status in {"RECEIVED", "CANCELLED"}:
            messages.error(request, "This purchase order cannot receive more stock.")
            return redirect("electronics:suppliers")
        for item in order.items.select_related("product").select_for_update():
            remaining = item.quantity - item.received_quantity
            if remaining <= 0:
                continue
            InventoryTransaction.objects.create(
                business=business,
                product=item.product,
                transaction_type="RECEIVED",
                quantity=remaining,
                unit_cost=item.unit_cost,
                reference_type="PURCHASE_ORDER",
                reference_id=str(order.id),
                reference_number=order.order_number,
                notes=f"Received from {order.supplier.name}",
                status="COMPLETED",
                created_by=request.user,
            )
            item.received_quantity = item.quantity
            item.save(update_fields=["received_quantity"])
        order.status = "RECEIVED"
        order.save(update_fields=["status"])
    messages.success(request, f"Stock for {order.order_number} has been received and inventory updated.")
    return redirect("electronics:suppliers")


@login_required
@business_required
def repair_list_view(request):
    business = _electronics_business(request)
    if business is None:
        return redirect("dashboard")
    jobs = RepairJob.objects.filter(business=business).select_related("customer", "technician")
    status = request.GET.get("status", "")
    search = request.GET.get("q", "").strip()
    if status in dict(RepairJob.STATUS_CHOICES):
        jobs = jobs.filter(status=status)
    if search:
        jobs = jobs.filter(
            Q(job_number__icontains=search)
            | Q(customer_name__icontains=search)
            | Q(customer_phone__icontains=search)
            | Q(device_brand__icontains=search)
            | Q(device_model__icontains=search)
            | Q(imei__icontains=search)
        )

    today = timezone.localdate()
    all_jobs = RepairJob.objects.filter(business=business)
    context = {
        "jobs": Paginator(jobs, 25).get_page(request.GET.get("page")),
        "search": search,
        "status_filter": status,
        "statuses": RepairJob.STATUS_CHOICES,
        "open_count": all_jobs.exclude(status__in=["COLLECTED", "CANCELLED"]).count(),
        "ready_count": all_jobs.filter(status="READY").count(),
        "completed_month": all_jobs.filter(status="COLLECTED", updated_at__date__gte=today.replace(day=1)).count(),
        "repair_revenue": all_jobs.filter(status="COLLECTED", updated_at__date__gte=today.replace(day=1)).aggregate(
            total=Sum("estimate")
        )["total"] or Decimal("0"),
        "page": "repairs",
    }
    return render(request, "electronics/repairs.html", context)


@login_required
@business_required
def repair_create_view(request):
    business = _electronics_business(request)
    if business is None:
        return redirect("dashboard")
    form = RepairJobForm(request.POST or None, business=business)
    if request.method == "POST" and form.is_valid():
        job = form.save(commit=False)
        job.business = business
        job.created_by = request.user
        job.save()
        messages.success(request, f"Repair job {job.job_number} created.")
        return redirect("electronics:repairs")
    return render(request, "electronics/repair_form.html", {"form": form, "page": "repairs"})


@login_required
@business_required
@require_POST
def repair_status_view(request, job_id):
    business = _electronics_business(request)
    if business is None:
        return redirect("dashboard")
    job = get_object_or_404(RepairJob, id=job_id, business=business)
    status = request.POST.get("status", "")
    if status not in dict(RepairJob.STATUS_CHOICES):
        messages.error(request, "Choose a valid repair status.")
        return redirect("electronics:repairs")
    job.status = status
    job.save(update_fields=["status", "updated_at"])
    messages.success(request, f"{job.job_number} updated to {job.get_status_display()}.")
    return redirect("electronics:repairs")


@login_required
@business_required
def customer_credit_view(request):
    business = _electronics_business(request)
    if business is None:
        return redirect("dashboard")

    form = CreditPlanForm(request.POST or None, business=business)
    if request.method == "POST" and form.is_valid():
        plan = form.save(commit=False)
        plan.business = business
        plan.save()
        messages.success(request, f"Installment plan saved for {plan.sale.sale_number}.")
        return redirect("electronics:customer_credit")

    today = timezone.localdate()
    credit_sales = list(
        Sale.objects.filter(business=business, payment_method="CREDIT", balance_due__gt=0)
        .select_related("customer")
        .prefetch_related("payments")
        .order_by("sale_date")
    )
    plans = {
        plan.sale_id: plan
        for plan in CreditPlan.objects.filter(business=business, sale__in=credit_sales)
    }
    overdue_sales = [
        sale for sale in credit_sales
        if sale.id in plans and plans[sale.id].next_due_date < today
    ]
    credit_rows = [
        {
            "sale": sale,
            "plan": plans.get(sale.id),
            "overdue": sale.id in plans and plans[sale.id].next_due_date < today,
        }
        for sale in credit_sales
    ]
    return render(request, "electronics/customer_credit.html", {
        "credit_rows": credit_rows,
        "plans": plans,
        "form": form,
        "outstanding_total": sum((sale.balance_due for sale in credit_sales), Decimal("0")),
        "overdue_total": sum((sale.balance_due for sale in overdue_sales), Decimal("0")),
        "customers_with_credit": len({sale.customer_id for sale in credit_sales if sale.customer_id}),
        "average_balance": (
            sum((sale.balance_due for sale in credit_sales), Decimal("0")) / len(credit_sales)
            if credit_sales else Decimal("0")
        ),
        "today": today,
        "page": "customer_credit",
    })


@login_required
@business_required
def electronics_dashboard_view(request, context):
    business = request.user.business
    today = timezone.localdate()
    month_start = today.replace(day=1)
    insights = BusinessInsight.objects.filter(
        business=business, is_dismissed=False
    ).order_by("-generated_at")[:2]
    top_product = SaleItem.objects.filter(
        sale__business=business, sale__sale_date__date__gte=today - timedelta(days=7)
    ).values("product__name", "product_id", "product__current_stock").annotate(
        units_sold=Sum("quantity")
    ).order_by("-units_sold").first()
    overdue_credit = Sale.objects.filter(
        business=business,
        payment_method="CREDIT",
        balance_due__gt=0,
        credit_plan__next_due_date__lt=today,
    ).aggregate(
        amount=Sum("balance_due"),
        customers=Count("customer", distinct=True),
    )
    context.update({
        "page": "dashboard",
        "today": today,
        "month_expenses": Expense.objects.filter(
            business=business, expense_date__gte=month_start, expense_date__lte=today
        ).aggregate(total=Sum("amount"))["total"] or 0,
        "top_product": top_product,
        "overdue_credit_amount": overdue_credit["amount"] or 0,
        "overdue_credit_customers": overdue_credit["customers"] or 0,
        "electronics_insights": insights,
        "recent_sales": Sale.objects.filter(business=business).select_related("customer").order_by("-sale_date")[:6],
        "low_stock_products": Product.objects.filter(
            business=business, is_active=True, current_stock__gt=0, current_stock__lte=F("reorder_level")
        ).order_by("current_stock", "name")[:5],
    })
    return render(request, "analytics/electronics_dashboard.html", context)
