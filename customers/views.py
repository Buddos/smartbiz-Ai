from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import business_required
from accounts.models import UserActivity
from .forms import CustomerFeedbackForm, CustomerForm
from .models import Customer


@login_required
@business_required
def customer_list_view(request):
    customers = Customer.objects.filter(business=request.user.business)
    search = request.GET.get("search", "")
    if search:
        customers = customers.filter(
            Q(name__icontains=search) | Q(phone__icontains=search) | Q(email__icontains=search)
        )
    customers = customers.annotate(order_count=Count("sales"), total_spent=Sum("sales__total"))
    page_obj = Paginator(customers, 20).get_page(request.GET.get("page"))
    return render(request, "customers/list.html", {
        "page_obj": page_obj,
        "search": search,
        "title": "Customers",
    })


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
    sales = customer.sales.all()[:20]
    feedback = customer.feedback.all()[:10]
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
    return render(request, "customers/detail.html", {
        "customer": customer,
        "sales": sales,
        "feedback": feedback,
        "fb_form": fb_form,
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
