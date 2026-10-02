import csv

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from datetime import timedelta
from django.views.decorators.http import require_POST

from accounts.decorators import business_required
from accounts.models import UserActivity
from .forms import CustomerFeedbackForm, CustomerForm
from .models import Customer
from sales.models import Sale


@login_required
@business_required
def customer_list_view(request):
    business = request.user.business
    all_customers = Customer.objects.filter(business=business, is_active=True)
    customers = (
        all_customers
        if business.business_type == "ELECTRONICS"
        else Customer.objects.filter(business=business)
    )
    search = request.GET.get("search", "").strip()
    if search:
        customers = customers.filter(
            Q(name__icontains=search) | Q(phone__icontains=search) | Q(email__icontains=search)
        )
    customers = customers.annotate(
        order_count=Count("sales", distinct=True),
        total_spent=Sum("sales__total"),
        last_purchase=Max("sales__sale_date"),
        outstanding_credit=Sum(
            "sales__balance_due",
            filter=Q(sales__payment_method="CREDIT", sales__balance_due__gt=0),
        ),
    )
    credit_filter = request.GET.get("credit", "")
    if credit_filter == "yes":
        customers = customers.filter(outstanding_credit__gt=0)
    elif credit_filter == "no":
        customers = customers.filter(Q(outstanding_credit__isnull=True) | Q(outstanding_credit=0))
    activity_filter = request.GET.get("activity", "")
    if activity_filter == "new":
        customers = customers.filter(created_at__date__gte=timezone.localdate().replace(day=1))
    elif activity_filter == "repeat":
        customers = customers.filter(order_count__gte=2)
    elif activity_filter == "inactive":
        customers = customers.filter(
            Q(last_purchase__isnull=True)
            | Q(last_purchase__lt=timezone.now() - timedelta(days=90))
        )

    page_obj = Paginator(customers.order_by("name"), 20).get_page(request.GET.get("page"))
    month_start = timezone.localdate().replace(day=1)
    purchased_customers = all_customers.annotate(order_count=Count("sales", distinct=True)).filter(
        order_count__gt=0
    )
    repeated_customers = purchased_customers.filter(order_count__gte=2).count()
    inactive_customers = all_customers.annotate(last_purchase=Max("sales__sale_date")).filter(
        Q(last_purchase__isnull=True)
        | Q(last_purchase__lt=timezone.now() - timedelta(days=90))
    ).count()
    outstanding_credit = Sale.objects.filter(
        business=business, payment_method="CREDIT", balance_due__gt=0
    )
    return render(request, (
        "electronics/customers.html"
        if business.business_type == "ELECTRONICS"
        else "customers/list.html"
    ), {
        "page_obj": page_obj,
        "search": search,
        "customer_count": all_customers.count(),
        "new_this_month": all_customers.filter(created_at__date__gte=month_start).count(),
        "repeat_rate": round(
            repeated_customers / purchased_customers.count() * 100
        ) if purchased_customers.exists() else 0,
        "repeat_customers": repeated_customers,
        "inactive_customers": inactive_customers,
        "credit_total": outstanding_credit.aggregate(total=Sum("balance_due"))["total"] or 0,
        "credit_customers": outstanding_credit.values("customer_id").distinct().count(),
        "credit_filter": credit_filter,
        "activity_filter": activity_filter,
        "current_month": timezone.localdate().strftime("%Y-%m"),
        "title": "Customers",
    })


@login_required
@business_required
def customer_export_view(request):
    customers = Customer.objects.filter(
        business=request.user.business, is_active=True
    ).annotate(
        order_count=Count("sales", distinct=True),
        total_spent=Sum("sales__total"),
        last_purchase=Max("sales__sale_date"),
        outstanding_credit=Sum(
            "sales__balance_due",
            filter=Q(sales__payment_method="CREDIT", sales__balance_due__gt=0),
        ),
    )
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="customers.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "Name", "Phone", "Email", "Last purchase", "Purchases",
        "Lifetime spend", "Outstanding credit",
    ])
    for customer in customers:
        writer.writerow([
            customer.name,
            customer.phone,
            customer.email,
            customer.last_purchase.isoformat() if customer.last_purchase else "",
            customer.order_count,
            customer.total_spent or 0,
            customer.outstanding_credit or 0,
        ])
    return response


@login_required
@business_required
def customer_create_view(request):
    if request.method == "POST":
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save(commit=False)
            customer.business = request.user.business
            customer.save()
            UserActivity.objects.create(
                user=request.user,
                action="CREATE",
                model_name="Customer",
                object_id=str(customer.id),
                business=request.user.business,
            )
            messages.success(request, f'Customer "{customer.name}" added.')
            return redirect("customers:detail", customer_id=customer.id)
    else:
        form = CustomerForm()
    return render(request, "customers/form.html", {"form": form, "title": "Add Customer"})


@login_required
@business_required
def customer_detail_view(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id, business=request.user.business)
    sales = customer.sales.all().order_by("-sale_date")[:20]
    feedback = customer.feedback.all()[:10]
    sales_summary = customer.sales.aggregate(
        purchases=Count("id"),
        spent=Sum("total"),
        balance=Sum("balance_due", filter=Q(payment_method="CREDIT", balance_due__gt=0)),
    )
    repair_jobs = []
    repair_job_count = 0
    if request.user.business.business_type == "ELECTRONICS":
        from electronics.models import RepairJob
        customer_repairs = RepairJob.objects.filter(
            business=request.user.business, customer=customer
        )
        repair_job_count = customer_repairs.count()
        repair_jobs = customer_repairs.order_by("-created_at")[:10]
    if request.method == "POST":
        fb_form = CustomerFeedbackForm(request.POST)
        if fb_form.is_valid():
            item = fb_form.save(commit=False)
            item.customer = customer
            item.business = request.user.business
            item.save()
            messages.success(request, "Feedback saved.")
            return redirect("customers:detail", customer_id=customer.id)
    else:
        fb_form = CustomerFeedbackForm()
    return render(request, (
        "electronics/customer_detail.html"
        if request.user.business.business_type == "ELECTRONICS"
        else "customers/detail.html"
    ), {
        "customer": customer,
        "sales": sales,
        "feedback": feedback,
        "fb_form": fb_form,
        "sales_summary": sales_summary,
        "repair_jobs": repair_jobs,
        "repair_job_count": repair_job_count,
        "title": customer.name,
    })


@login_required
@business_required
def customer_update_view(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id, business=request.user.business)
    if request.method == "POST":
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            messages.success(request, "Customer updated.")
            return redirect("customers:detail", customer_id=customer.id)
    else:
        form = CustomerForm(instance=customer)
    return render(request, "customers/form.html", {"form": form, "customer": customer, "title": "Edit Customer"})


@login_required
@business_required
@require_POST
def customer_delete_view(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id, business=request.user.business)
    customer.delete()
    messages.success(request, "Customer deleted.")
    return redirect("customers:list")
