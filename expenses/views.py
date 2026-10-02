import csv
from calendar import monthrange

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from datetime import date, timedelta
from django.views.decorators.http import require_POST

from accounts.decorators import business_required, permission_required
from accounts.models import UserActivity
from .forms import ExpenseCategoryForm, ExpenseForm, RecurringExpenseForm
from .models import Expense, ExpenseCategory, RecurringExpense


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
@permission_required('review_expenses')
def expense_list_view(request):
    business = request.user.business
    ensure_default_categories(business)
    today = timezone.localdate()
    month_start = today.replace(day=1)
    previous_month_end = month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    all_expenses = Expense.objects.filter(business=business)
    recurring_form = RecurringExpenseForm(business=business)
    if request.method == "POST" and request.POST.get("form_type") == "recurring":
        if not request.user.has_permission("submit_expenses"):
            messages.error(request, "You do not have permission to create recurring expense schedules.")
            return redirect("expenses:list")
        recurring_form = RecurringExpenseForm(request.POST, business=business)
        if recurring_form.is_valid():
            schedule = recurring_form.save(commit=False)
            schedule.business = business
            schedule.created_by = request.user
            schedule.save()
            messages.success(request, f"Recurring schedule for {schedule.title} was saved.")
            return redirect("expenses:list")
    expenses = all_expenses
    search = request.GET.get("search", "")
    if search:
        expenses = expenses.filter(Q(title__icontains=search) | Q(vendor__icontains=search))
    category = request.GET.get("category")
    if category:
        expenses = expenses.filter(category_id=category)
    payment_method = request.GET.get("payment_method", "")
    if payment_method in dict(Expense.PAYMENT_METHODS):
        expenses = expenses.filter(payment_method=payment_method)
    default_period = "this_month" if business.business_type == "ELECTRONICS" else "all"
    period = request.GET.get("period", default_period)
    if period == "this_month":
        expenses = expenses.filter(expense_date__gte=month_start, expense_date__lte=today)
    elif period == "last_month":
        expenses = expenses.filter(expense_date__gte=previous_month_start, expense_date__lte=previous_month_end)
    elif period == "custom":
        for param, field in (("date_from", "expense_date__gte"), ("date_to", "expense_date__lte")):
            raw_date = request.GET.get(param, "")
            if raw_date:
                try:
                    expenses = expenses.filter(**{field: date.fromisoformat(raw_date)})
                except ValueError:
                    messages.error(request, f"Invalid {param.replace('_', ' ')} filter.")
    page_obj = Paginator(expenses, 20).get_page(request.GET.get("page"))
    total = expenses.aggregate(total=Sum("amount"))["total"] or 0
    month_total = all_expenses.filter(
        expense_date__gte=month_start, expense_date__lte=today
    ).aggregate(total=Sum("amount"))["total"] or 0
    previous_month_total = all_expenses.filter(
        expense_date__gte=previous_month_start, expense_date__lte=previous_month_end
    ).aggregate(total=Sum("amount"))["total"] or 0
    biggest_category = all_expenses.filter(
        expense_date__gte=month_start, expense_date__lte=today
    ).values("category__name").annotate(amount=Sum("amount")).order_by("-amount").first()
    expense_breakdown = list(
        all_expenses.filter(
            expense_date__gte=month_start, expense_date__lte=today
        ).values("category__name").annotate(amount=Sum("amount")).order_by("-amount")
    )
    breakdown_total = sum((row["amount"] for row in expense_breakdown), 0)
    chart_colors = ["#1b7a4d", "#4a7fc1", "#f0a13b", "#e35d34", "#8064a2", "#92a0ad"]
    for index, row in enumerate(expense_breakdown):
        row["category__name"] = row["category__name"] or "Uncategorized"
        row["color"] = chart_colors[index % len(chart_colors)]
        row["share"] = (row["amount"] / breakdown_total * 100) if breakdown_total else 0
    if biggest_category:
        biggest_category["category__name"] = biggest_category["category__name"] or "Uncategorized"
    cursor = 0
    chart_stops = []
    for row in expense_breakdown:
        next_cursor = cursor + float(row["share"])
        chart_stops.append(f'{row["color"]} {cursor:.1f}% {next_cursor:.1f}%')
        cursor = next_cursor
    return render(request, (
        "electronics/expenses.html"
        if business.business_type == "ELECTRONICS"
        else "expenses/list.html"
    ), {
        "page_obj": page_obj,
        "search": search,
        "total": total,
        "categories": ExpenseCategory.objects.filter(business=business),
        "payment_methods": Expense.PAYMENT_METHODS,
        "payment_method_filter": payment_method,
        "period": period,
        "today": today,
        "date_from": request.GET.get("date_from", ""),
        "date_to": request.GET.get("date_to", ""),
        "month_total": month_total,
        "month_difference": month_total - previous_month_total,
        "breakdown_total": breakdown_total,
        "month_count": all_expenses.filter(
            expense_date__gte=month_start, expense_date__lte=today
        ).count(),
        "previous_month_total": previous_month_total,
        "month_change": (
            (month_total - previous_month_total) / previous_month_total * 100
            if previous_month_total else None
        ),
        "biggest_category": biggest_category,
        "expense_breakdown": expense_breakdown,
        "expense_chart_gradient": ", ".join(chart_stops),
        "expense_count": expenses.count(),
        "recurring_form": recurring_form,
        "recurring_schedules": RecurringExpense.objects.filter(
            business=business
        ).select_related("category").order_by("-is_active", "next_due_date"),
        "can_manage_recurring": request.user.has_permission("submit_expenses"),
        "can_approve_recurring": request.user.has_permission("approve_expenses"),
        "title": "Expenses",
    })


@login_required
@business_required
@permission_required("review_expenses")
def expense_export_view(request):
    business = request.user.business
    expenses = Expense.objects.filter(business=business).select_related("category")
    search = request.GET.get("search", "").strip()
    if search:
        expenses = expenses.filter(Q(title__icontains=search) | Q(vendor__icontains=search))
    category = request.GET.get("category", "")
    if category:
        expenses = expenses.filter(category_id=category)
    payment_method = request.GET.get("payment_method", "")
    if payment_method in dict(Expense.PAYMENT_METHODS):
        expenses = expenses.filter(payment_method=payment_method)
    period = request.GET.get("period", "all")
    today = timezone.localdate()
    month_start = today.replace(day=1)
    previous_month_end = month_start - timedelta(days=1)
    if period == "this_month":
        expenses = expenses.filter(expense_date__gte=month_start, expense_date__lte=today)
    elif period == "last_month":
        expenses = expenses.filter(expense_date__gte=previous_month_end.replace(day=1), expense_date__lte=previous_month_end)
    elif period == "custom":
        for param, field in (("date_from", "expense_date__gte"), ("date_to", "expense_date__lte")):
            raw_date = request.GET.get(param, "")
            if raw_date:
                try:
                    expenses = expenses.filter(**{field: date.fromisoformat(raw_date)})
                except ValueError:
                    messages.error(request, f"Invalid {param.replace('_', ' ')} filter.")
                    return redirect("expenses:list")
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="expenses.csv"'
    writer = csv.writer(response)
    writer.writerow(["Date", "Category", "Description", "Vendor", "Amount", "Payment method", "Receipt"])
    for expense in expenses.order_by("-expense_date", "-created_at"):
        writer.writerow([
            expense.expense_date.isoformat(),
            expense.category.name if expense.category else "Uncategorized",
            expense.title,
            expense.vendor,
            expense.amount,
            expense.get_payment_method_display(),
            expense.receipt.name if expense.receipt else "",
        ])
    return response


def _next_recurring_date(schedule, due_date):
    if schedule.frequency == "WEEKLY":
        return due_date + timedelta(days=7)
    months = 3 if schedule.frequency == "QUARTERLY" else 1
    month_index = due_date.month - 1 + months
    year = due_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(schedule.anchor_day or due_date.day, monthrange(year, month)[1])
    return date(year, month, day)


@login_required
@business_required
@require_POST
@permission_required("approve_expenses")
def recurring_expense_confirm_view(request, schedule_id):
    business = request.user.business
    today = timezone.localdate()
    with transaction.atomic():
        schedule = get_object_or_404(
            RecurringExpense.objects.select_for_update(),
            id=schedule_id,
            business=business,
            is_active=True,
        )
        due_date = schedule.next_due_date
        if due_date > today:
            messages.error(request, "This recurring expense is not due yet.")
            return redirect("expenses:list")
        if Expense.objects.filter(
            recurring_schedule=schedule,
            recurring_due_date=due_date,
        ).exists():
            messages.error(request, "This due occurrence has already been recorded.")
            return redirect("expenses:list")
        Expense.objects.create(
            business=business,
            category=schedule.category,
            title=schedule.title,
            amount=schedule.amount,
            expense_date=due_date,
            payment_method=schedule.payment_method,
            vendor=schedule.vendor,
            notes=schedule.notes,
            recurring_schedule=schedule,
            recurring_due_date=due_date,
            created_by=request.user,
        )
        schedule.next_due_date = _next_recurring_date(schedule, due_date)
        schedule.save(update_fields=["next_due_date"])
    messages.success(request, f"Expense for {schedule.title} was confirmed and recorded.")
    return redirect("expenses:list")


@login_required
@business_required
@require_POST
@permission_required("approve_expenses")
def recurring_expense_toggle_view(request, schedule_id):
    schedule = get_object_or_404(
        RecurringExpense,
        id=schedule_id,
        business=request.user.business,
    )
    schedule.is_active = not schedule.is_active
    schedule.save(update_fields=["is_active"])
    messages.success(
        request,
        f"Recurring schedule for {schedule.title} "
        f"{'resumed' if schedule.is_active else 'paused'}.",
    )
    return redirect("expenses:list")


@login_required
@business_required
@permission_required('submit_expenses')
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
@permission_required('submit_expenses')
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
@permission_required('approve_expenses')
def expense_delete_view(request, expense_id):
    expense = get_object_or_404(Expense, id=expense_id, business=request.user.business)
    expense.delete()
    messages.success(request, "Expense deleted.")
    return redirect("expenses:list")


@login_required
@business_required
@permission_required('approve_expenses')
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
