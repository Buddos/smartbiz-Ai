from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import business_required
from accounts.models import UserActivity
from .forms import ExpenseCategoryForm, ExpenseForm
from .models import Expense, ExpenseCategory


DEFAULT_CATEGORIES = [
    "Rent",
    "Utilities",
    "Transport",
    "Salaries",
    "Purchases",
    "Marketing",
    "Other",
]


def ensure_default_categories(business):
    for name in DEFAULT_CATEGORIES:
        ExpenseCategory.objects.get_or_create(business=business, name=name)


@login_required
@business_required
def expense_list_view(request):
    business = request.user.business
    ensure_default_categories(business)
    expenses = Expense.objects.filter(business=business)
    search = request.GET.get("search", "")
    if search:
        expenses = expenses.filter(Q(title__icontains=search) | Q(vendor__icontains=search))
    category = request.GET.get("category")
    if category:
        expenses = expenses.filter(category_id=category)
    page_obj = Paginator(expenses, 20).get_page(request.GET.get("page"))
    total = expenses.aggregate(total=Sum("amount"))["total"] or 0
    return render(request, "expenses/list.html", {
        "page_obj": page_obj,
        "search": search,
        "total": total,
        "categories": ExpenseCategory.objects.filter(business=business),
        "title": "Expenses",
    })


@login_required
@business_required
def expense_create_view(request):
    ensure_default_categories(request.user.business)
    if request.method == "POST":
        form = ExpenseForm(request.POST, request.FILES, business=request.user.business)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.business = request.user.business
            expense.created_by = request.user
            expense.save()
            UserActivity.objects.create(
                user=request.user,
                action="CREATE",
                model_name="Expense",
                object_id=str(expense.id),
                business=request.user.business,
            )
            messages.success(request, "Expense recorded.")
            return redirect("expenses:list")
    else:
        form = ExpenseForm(business=request.user.business)
    return render(request, "expenses/form.html", {"form": form, "title": "Add Expense"})


@login_required
@business_required
def expense_update_view(request, expense_id):
    expense = get_object_or_404(Expense, id=expense_id, business=request.user.business)
    if request.method == "POST":
        form = ExpenseForm(
            request.POST, request.FILES, instance=expense, business=request.user.business
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Expense updated.")
            return redirect("expenses:list")
    else:
        form = ExpenseForm(instance=expense, business=request.user.business)
    return render(request, "expenses/form.html", {"form": form, "expense": expense, "title": "Edit Expense"})


@login_required
@business_required
@require_POST
def expense_delete_view(request, expense_id):
    expense = get_object_or_404(Expense, id=expense_id, business=request.user.business)
    expense.delete()
    messages.success(request, "Expense deleted.")
    return redirect("expenses:list")


@login_required
@business_required
def category_create_view(request):
    if request.method == "POST":
        form = ExpenseCategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.business = request.user.business
            category.save()
            messages.success(request, "Category added.")
            return redirect("expenses:list")
    else:
        form = ExpenseCategoryForm()
    return render(request, "expenses/category_form.html", {"form": form, "title": "Expense Category"})
