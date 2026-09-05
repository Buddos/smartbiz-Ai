from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import business_required, role_required
from expenses.models import Expense
from products.models import Product
from sales.models import Sale, SaleItem
from ai_engine.models import AIInsight, AIRecommendation
from .models import Report


def _period(request):
    end = timezone.now().date()
    start = end - timedelta(days=30)
    raw_start = request.GET.get("start")
    raw_end = request.GET.get("end")
    if raw_start:
        start = timezone.datetime.fromisoformat(raw_start).date()
    if raw_end:
        end = timezone.datetime.fromisoformat(raw_end).date()
    return start, end


def _build_summary(business, start, end):
    sales = Sale.objects.filter(business=business, sale_date__date__range=[start, end])
    expenses = Expense.objects.filter(business=business, expense_date__range=[start, end])
    revenue = sales.aggregate(t=Sum("total"))["t"] or 0
    expense_total = expenses.aggregate(t=Sum("amount"))["t"] or 0
    top = (
        SaleItem.objects.filter(sale__business=business, sale__sale_date__date__range=[start, end])
        .values("product__name")
        .annotate(revenue=Sum("total"), qty=Sum("quantity"))
        .order_by("-revenue")[:5]
    )
    low_stock = Product.objects.filter(
        business=business, is_active=True, current_stock__lte=F("reorder_level")
    ).count()
    return {
        "revenue": float(revenue),
        "expenses": float(expense_total),
        "net": float(revenue - expense_total),
        "sales_count": sales.count(),
        "low_stock": low_stock,
        "top_products": list(top),
        "insights": AIInsight.objects.filter(business=business, created_at__date__range=[start, end]).count(),
        "open_recommendations": AIRecommendation.objects.filter(business=business, status="OPEN").count(),
    }


@login_required
@business_required
@role_required(["OWNER", "MANAGER", "ADMIN", "SUPER_ADMIN"])
def report_list_view(request):
    start, end = _period(request)
    reports = Report.objects.filter(business=request.user.business)
    return render(request, "reports/list.html", {
        "reports": reports,
        "start": start,
        "end": end,
        "title": "Reports",
    })


@login_required
@business_required
@role_required(["OWNER", "MANAGER", "ADMIN", "SUPER_ADMIN"])
def report_generate_view(request):
    start, end = _period(request)
    report_type = request.GET.get("type", "PERFORMANCE")
    if report_type not in dict(Report.REPORT_TYPES):
        report_type = "PERFORMANCE"
    summary = _build_summary(request.user.business, start, end)
    report = Report.objects.create(
        business=request.user.business,
        report_type=report_type,
        title=f"{dict(Report.REPORT_TYPES)[report_type]} ({start} to {end})",
        period_start=start,
        period_end=end,
        summary=summary,
        created_by=request.user,
    )
    messages.success(request, "Report generated from recorded business data.")
    return redirect("reports:detail", report_id=report.id)


@login_required
@business_required
@role_required(["OWNER", "MANAGER", "ADMIN", "SUPER_ADMIN"])
def report_detail_view(request, report_id):
    report = get_object_or_404(Report, id=report_id, business=request.user.business)
    return render(request, "reports/detail.html", {"report": report, "title": report.title})
