from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import business_required
from analytics.models import BusinessInsight
from businesses.models import Business
from customers.models import Customer
from expenses.models import Expense
from inventory.models import InventoryTransaction
from products.models import Product
from sales.models import Payment, Sale, SaleItem

from .forms import (
    CashDrawerPayoutForm,
    DrawerCloseForm,
    DrawerOpenForm,
    RetailPurchaseOrderForm,
    RetailPurchaseOrderItemFormSet,
    RetailSupplierForm,
)
from .models import (
    CashDrawerSession,
    RetailCreditDue,
    RetailPurchaseOrder,
    RetailPurchaseOrderItem,
    RetailSupplier,
)


def retail_workspace_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        business = request.user.business
        if business is None or business.business_type != "RETAIL":
            messages.error(request, "This workspace is only available to retail businesses.")
            return redirect("dashboard")
        return view(request, *args, **kwargs)
    return wrapped


def _drawer_totals(session, as_of=None):
    as_of = as_of or timezone.now()
    cash_sales = Sale.objects.filter(
        business=session.business,
        payment_method="CASH",
        order_status="COMPLETED",
        sale_date__gte=session.opened_at,
        sale_date__lte=as_of,
    ).aggregate(total=Sum("amount_paid"))["total"] or Decimal("0")
    credit_cash_payments = Payment.objects.filter(
        business=session.business,
        sale__payment_method="CREDIT",
        payment_method="CASH",
        payment_status="COMPLETED",
        payment_date__gte=session.opened_at,
        payment_date__lte=as_of,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    cash_out = session.payouts.filter(created_at__gte=session.opened_at, created_at__lte=as_of).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0")
    cash_sales += credit_cash_payments
    return cash_sales, cash_out, session.opening_balance + cash_sales - cash_out


@login_required
@business_required
@retail_workspace_required
def retail_dashboard_view(request):
    business = request.user.business
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    today_sales = Sale.objects.filter(
        business=business,
        sale_date__date=today,
        order_status="COMPLETED",
    )
    yesterday_sales = Sale.objects.filter(
        business=business,
        sale_date__date=yesterday,
        order_status="COMPLETED",
    )
    today_revenue = today_sales.aggregate(total=Sum("total"))["total"] or Decimal("0")
    yesterday_revenue = yesterday_sales.aggregate(total=Sum("total"))["total"] or Decimal("0")
    revenue_change = (
        (today_revenue - yesterday_revenue) * Decimal("100") / yesterday_revenue
        if yesterday_revenue else Decimal("0")
    )
    cost_of_goods = SaleItem.objects.filter(
        sale__in=today_sales
    ).aggregate(total=Sum(F("quantity") * F("cost_price")))["total"] or Decimal("0")
    gross_profit = today_revenue - cost_of_goods
    total_products = Product.objects.filter(business=business, is_active=True)
    low_stock = total_products.filter(
        current_stock__gt=0, current_stock__lte=F("reorder_level")
    ).count()
    out_of_stock = total_products.filter(current_stock=0).count()
    stock_value = total_products.aggregate(
        total=Sum(F("current_stock") * F("purchase_price"))
    )["total"] or Decimal("0")
    new_customers = Customer.objects.filter(
        business=business,
        is_active=True,
        created_at__date=today,
    ).count()
    top_sellers = SaleItem.objects.filter(
        sale__business=business,
        sale__sale_date__date=today,
        sale__order_status="COMPLETED",
    ).values("product_id", "product__name", "product__current_stock").annotate(
        units_sold=Sum("quantity"),
        revenue=Sum("total"),
    ).order_by("-units_sold")[:5]
    open_credit = Sale.objects.filter(
        business=business,
        payment_method="CREDIT",
        balance_due__gt=0,
    ).aggregate(total=Sum("balance_due"), customers=Count("customer", distinct=True))
    drawer = CashDrawerSession.objects.filter(business=business, closed_at__isnull=True).first()
    drawer_expected = _drawer_totals(drawer)[2] if drawer else None
    insights = BusinessInsight.objects.filter(
        business=business,
        is_dismissed=False,
    ).order_by("-generated_at")[:3]
    return render(request, "retail/dashboard.html", {
        "title": "Retail Dashboard",
        "today": today,
        "today_revenue": today_revenue,
        "today_transactions": today_sales.count(),
        "average_ticket": today_revenue / today_sales.count() if today_sales.exists() else Decimal("0"),
        "gross_profit": gross_profit,
        "gross_margin": gross_profit * Decimal("100") / today_revenue if today_revenue else Decimal("0"),
        "customers_served": today_sales.exclude(Q(customer__isnull=True) & Q(customer_name="")).count(),
        "new_customers": new_customers,
        "revenue_change": revenue_change,
        "total_products": total_products.count(),
        "low_stock_count": low_stock,
        "out_of_stock_count": out_of_stock,
        "stock_value": stock_value,
        "top_sellers": top_sellers,
        "insights": insights,
        "open_credit_total": open_credit["total"] or Decimal("0"),
        "customers_with_credit": open_credit["customers"],
        "drawer": drawer,
        "drawer_expected": drawer_expected,
        "month_expenses": Expense.objects.filter(
            business=business, expense_date__year=today.year, expense_date__month=today.month
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0"),
    })


@login_required
@business_required
@retail_workspace_required
def supplier_list_view(request):
    business = request.user.business
    supplier_form = RetailSupplierForm(prefix="supplier")
    order_form = RetailPurchaseOrderForm(prefix="order", business=business)
    item_formset = RetailPurchaseOrderItemFormSet(
        prefix="items", form_kwargs={"business": business}
    )
    if request.method == "POST" and request.POST.get("form_type") == "supplier":
        supplier_form = RetailSupplierForm(request.POST, prefix="supplier")
        if supplier_form.is_valid():
            supplier = supplier_form.save(commit=False)
            supplier.business = business
            supplier.save()
            messages.success(request, f"Supplier {supplier.name} added.")
            return redirect("retail:suppliers")
    elif request.method == "POST" and request.POST.get("form_type") == "order":
        order_form = RetailPurchaseOrderForm(request.POST, prefix="order", business=business)
        item_formset = RetailPurchaseOrderItemFormSet(
            request.POST, prefix="items", form_kwargs={"business": business}
        )
        if order_form.is_valid() and item_formset.is_valid():
            with transaction.atomic():
                order = order_form.save(commit=False)
                order.business = business
                order.created_by = request.user
                order.save()
                items = []
                for line in item_formset.cleaned_data:
                    if not line or not line.get("product") or line.get("DELETE"):
                        continue
                    product = line["product"]
                    if product.business_id != business.id:
                        raise ValueError("Purchase order product does not belong to this business.")
                    items.append(RetailPurchaseOrderItem(
                        order=order,
                        product=product,
                        quantity=line["quantity"],
                        unit_cost=line["unit_cost"],
                    ))
                RetailPurchaseOrderItem.objects.bulk_create(items)
                order.total = sum((item.line_total for item in items), Decimal("0"))
                order.save(update_fields=["total"])
            messages.success(request, f"Purchase order {order.order_number} created.")
            return redirect("retail:suppliers")
    suppliers = RetailSupplier.objects.filter(business=business, is_active=True)
    orders = RetailPurchaseOrder.objects.filter(
        business=business
    ).select_related("supplier").prefetch_related("items__product")[:30]
    return render(request, "retail/suppliers.html", {
        "title": "Suppliers",
        "supplier_form": supplier_form,
        "order_form": order_form,
        "item_formset": item_formset,
        "suppliers": suppliers,
        "orders": orders,
    })


@login_required
@business_required
@retail_workspace_required
@require_POST
def purchase_order_receive_view(request, order_id):
    business = request.user.business
    with transaction.atomic():
        order = get_object_or_404(
            RetailPurchaseOrder.objects.select_for_update().prefetch_related("items__product"),
            id=order_id,
            business=business,
        )
        if order.status in {"RECEIVED", "CANCELLED"}:
            messages.error(request, "This purchase order cannot receive more stock.")
            return redirect("retail:suppliers")
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
    messages.success(request, f"Stock for {order.order_number} has been received.")
    return redirect("retail:suppliers")


@login_required
@business_required
@retail_workspace_required
def cash_drawer_view(request):
    business = request.user.business
    active_session = CashDrawerSession.objects.filter(
        business=business, closed_at__isnull=True
    ).first()
    open_form = DrawerOpenForm()
    close_form = DrawerCloseForm()
    payout_form = CashDrawerPayoutForm()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "open":
            open_form = DrawerOpenForm(request.POST)
            if open_form.is_valid():
                with transaction.atomic():
                    Business.objects.select_for_update().get(pk=business.pk)
                    active = CashDrawerSession.objects.filter(
                        business=business, closed_at__isnull=True
                    ).exists()
                    if active:
                        messages.error(request, "A drawer is already open.")
                    else:
                        CashDrawerSession.objects.create(
                            business=business,
                            opened_by=request.user,
                            opening_balance=open_form.cleaned_data["opening_balance"],
                            expected_balance=open_form.cleaned_data["opening_balance"],
                            notes=open_form.cleaned_data["notes"],
                        )
                        messages.success(request, "Cash drawer opened.")
                return redirect("retail:cash_drawer")
        elif action == "close" and active_session:
            close_form = DrawerCloseForm(request.POST)
            if close_form.is_valid():
                _, _, expected = _drawer_totals(active_session)
                counted = close_form.cleaned_data["counted_balance"]
                variance = counted - expected
                reason = close_form.cleaned_data["variance_reason"].strip()
                if variance and not reason:
                    close_form.add_error("variance_reason", "Explain the variance before closing.")
                else:
                    active_session.closed_by = request.user
                    active_session.closed_at = timezone.now()
                    active_session.expected_balance = expected
                    active_session.counted_balance = counted
                    active_session.variance = variance
                    active_session.variance_reason = reason
                    active_session.save(update_fields=[
                        "closed_by", "closed_at", "expected_balance",
                        "counted_balance", "variance", "variance_reason",
                    ])
                    messages.success(request, "Cash drawer closed and reconciled.")
                    return redirect("retail:cash_drawer")
        elif action == "payout" and active_session:
            payout_form = CashDrawerPayoutForm(request.POST)
            if payout_form.is_valid():
                _, _, expected = _drawer_totals(active_session)
                if payout_form.cleaned_data["amount"] > expected:
                    payout_form.add_error("amount", "Payout cannot exceed the expected drawer balance.")
                else:
                    payout = payout_form.save(commit=False)
                    payout.session = active_session
                    payout.created_by = request.user
                    payout.save()
                    messages.success(request, "Cash payout recorded.")
                    return redirect("retail:cash_drawer")
        else:
            messages.error(request, "Open a drawer before recording payouts or closing it.")
    cash_sales = cash_out = drawer_expected = None
    payouts = []
    if active_session:
        cash_sales, cash_out, drawer_expected = _drawer_totals(active_session)
        payouts = active_session.payouts.all()
    history = CashDrawerSession.objects.filter(business=business).select_related(
        "opened_by", "closed_by"
    )[:20]
    last_closed = CashDrawerSession.objects.filter(
        business=business,
        closed_at__isnull=False,
    ).first()
    return render(request, "retail/cash_drawer.html", {
        "title": "Cash Drawer",
        "active_session": active_session,
        "open_form": open_form,
        "close_form": close_form,
        "payout_form": payout_form,
        "cash_sales": cash_sales,
        "cash_out": cash_out,
        "drawer_expected": drawer_expected,
        "payouts": payouts,
        "history": history,
        "last_closed": last_closed,
    })


@login_required
@business_required
@retail_workspace_required
def credit_view(request):
    business = request.user.business
    if request.method == "POST":
        action = request.POST.get("action")
        sale_id = request.POST.get("sale_id")
        if action == "due_date":
            sale = get_object_or_404(
                Sale, id=sale_id, business=business, payment_method="CREDIT", balance_due__gt=0
            )
            due_date = request.POST.get("due_date") or None
            try:
                due_date = datetime.strptime(due_date, "%Y-%m-%d").date() if due_date else None
            except ValueError:
                messages.error(request, "Enter a valid due date.")
            else:
                RetailCreditDue.objects.update_or_create(
                    business=business, sale=sale, defaults={"due_date": due_date}
                )
                messages.success(request, f"Due date updated for {sale.sale_number}.")
            return redirect("retail:credit")
        if action == "payment":
            try:
                amount = Decimal(request.POST.get("amount", "0"))
            except InvalidOperation:
                amount = Decimal("0")
            method = request.POST.get("payment_method", "")
            if method not in {"CASH", "M-PESA", "BANK", "CARD", "OTHER"} or amount <= 0:
                messages.error(request, "Enter a valid payment amount and payment method.")
                return redirect("retail:credit")
            with transaction.atomic():
                sale = get_object_or_404(
                    Sale.objects.select_for_update(),
                    id=sale_id,
                    business=business,
                    payment_method="CREDIT",
                    balance_due__gt=0,
                )
                if amount > sale.balance_due:
                    messages.error(request, "Payment cannot exceed the outstanding balance.")
                    return redirect("retail:credit")
                Payment.objects.create(
                    sale=sale,
                    business=business,
                    amount=amount,
                    payment_method=method,
                    payment_status="COMPLETED",
                    reference_number=request.POST.get("reference_number", "").strip(),
                    notes=request.POST.get("notes", "").strip(),
                    created_by=request.user,
                )
                sale.amount_paid += amount
                sale.save(update_fields=["amount_paid", "balance_due", "payment_status", "updated_at"])
            messages.success(request, f"Payment recorded for {sale.sale_number}.")
            return redirect("retail:credit")
        messages.error(request, "Choose a valid credit action.")
        return redirect("retail:credit")

    today = timezone.localdate()
    sales = list(
        Sale.objects.filter(
            business=business,
            payment_method="CREDIT",
            balance_due__gt=0,
        ).select_related("customer").prefetch_related("payments").order_by("sale_date")
    )
    due_dates = {
        due.sale_id: due
        for due in RetailCreditDue.objects.filter(business=business, sale__in=sales)
    }
    rows = [
        {"sale": sale, "due": due_dates.get(sale.id),
         "overdue": bool(
             due_dates.get(sale.id)
             and due_dates[sale.id].due_date
             and due_dates[sale.id].due_date < today
         )}
        for sale in sales
    ]
    balances = [sale.balance_due for sale in sales]
    return render(request, "retail/credit.html", {
        "title": "Debts & Credit",
        "rows": rows,
        "today": today,
        "outstanding_total": sum(balances, Decimal("0")),
        "overdue_total": sum(
            (row["sale"].balance_due for row in rows if row["overdue"]), Decimal("0")
        ),
        "customer_count": len({sale.customer_id for sale in sales if sale.customer_id}),
        "average_balance": sum(balances, Decimal("0")) / len(sales) if sales else Decimal("0"),
    })
