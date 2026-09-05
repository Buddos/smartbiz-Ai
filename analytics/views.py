from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db import models, transaction
from django.db.models import Q, Sum, Count, Avg, F, Max, Min
from django.utils import timezone
from django.views.decorators.http import require_POST
from datetime import datetime, timedelta, date
import json
import calendar

from businesses.models import Business
from sales.models import Sale, SaleItem, Payment
from products.models import Product, Category
from customers.models import Customer
from expenses.models import Expense
from inventory.models import InventoryTransaction, InventoryAlert
from .models import DashboardWidget, BusinessMetric, BusinessInsight, ExportLog

from accounts.decorators import business_required, role_required
from accounts.models import UserActivity
from ai_engine.services import run_intelligence_pipeline

# === Main Dashboard ===

@login_required
@business_required
def dashboard_view(request):
    """Main business dashboard."""
    business = request.user.business
    
    # Date range (last 30 days)
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=30)
    
    # Get dashboard data
    context = get_dashboard_data(business, start_date, end_date)
    context['title'] = 'Dashboard'
    
    return render(request, 'analytics/dashboard.html', context)


@login_required
@business_required
@role_required(["OWNER", "MANAGER"])
def business_admin_dashboard_view(request):
    """Business administration dashboard for authorized in-app users."""
    business = request.user.business
    activity = UserActivity.objects.filter(user__business=business).select_related("user")
    return render(request, "analytics/business_admin.html", {
        "business": business,
        "team_count": business.users.filter(is_active=True).count(),
        "product_count": Product.objects.filter(business=business, is_active=True).count(),
        "customer_count": Customer.objects.filter(business=business, is_active=True).count(),
        "sales_count": Sale.objects.filter(business=business).count(),
        "open_alert_count": InventoryAlert.objects.filter(business=business, status="ACTIVE").count(),
        "open_insight_count": BusinessInsight.objects.filter(
            business=business, is_dismissed=False, is_read=False
        ).count(),
        "team_members": business.users.order_by("first_name", "last_name")[:8],
        "recent_activity": activity.order_by("-timestamp")[:8],
        "recent_sales": Sale.objects.filter(business=business).order_by("-sale_date")[:6],
    })

def get_dashboard_data(business, start_date, end_date):
    """Get all dashboard data."""
    
    # Sales Data
    sales = Sale.objects.filter(
        business=business,
        sale_date__date__range=[start_date, end_date]
    )
    
    total_revenue = sales.aggregate(total=Sum('total'))['total'] or 0
    total_sales = sales.count()
    average_order_value = total_revenue / total_sales if total_sales > 0 else 0
    
    # Previous period comparison
    prev_start = start_date - timedelta(days=30)
    prev_end = start_date - timedelta(days=1)
    prev_sales = Sale.objects.filter(
        business=business,
        sale_date__date__range=[prev_start, prev_end]
    )
    prev_revenue = prev_sales.aggregate(total=Sum('total'))['total'] or 0
    
    revenue_growth = ((total_revenue - prev_revenue) / prev_revenue * 100) if prev_revenue > 0 else 0
    
    # Products Data
    total_products = Product.objects.filter(business=business, is_active=True).count()
    low_stock_count = Product.objects.filter(
        business=business,
        current_stock__lte=models.F('reorder_level'),
        current_stock__gt=0,
        is_active=True
    ).count()
    out_of_stock_count = Product.objects.filter(
        business=business,
        current_stock=0,
        is_active=True
    ).count()
    
    # Customers Data
    total_customers = Customer.objects.filter(business=business, is_active=True).count()
    new_customers = Customer.objects.filter(
        business=business,
        created_at__date__range=[start_date, end_date]
    ).count()
    
    # Expenses Data
    expenses = Expense.objects.filter(
        business=business,
        expense_date__range=[start_date, end_date]
    )
    total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or 0
    
    # Profit
    total_profit = total_revenue - total_expenses
    
    # Sales by day (for chart)
    daily_sales = sales.extra(
        select={'date': "date(sale_date)"}
    ).values('date').annotate(
        total=Sum('total'),
        count=Count('id')
    ).order_by('date')
    
    # Sales by category
    sales_by_category = SaleItem.objects.filter(
        sale__business=business,
        sale__sale_date__date__range=[start_date, end_date]
    ).values('product__category__name').annotate(
        total_sales=Sum('total'),
        total_quantity=Sum('quantity')
    ).order_by('-total_sales')
    
    # Top products
    top_products = SaleItem.objects.filter(
        sale__business=business,
        sale__sale_date__date__range=[start_date, end_date]
    ).values('product__name', 'product__sku').annotate(
        total_sold=Sum('quantity'),
        total_revenue=Sum('total')
    ).order_by('-total_revenue')[:10]
    
    # Recent insights
    recent_insights = BusinessInsight.objects.filter(
        business=business,
        is_dismissed=False
    ).order_by('-generated_at')[:5]
    
    # Unread insights count
    unread_insights = BusinessInsight.objects.filter(
        business=business,
        is_read=False,
        is_dismissed=False
    ).count()
    
    # Payment method breakdown
    payment_methods = sales.values('payment_method').annotate(
        total=Sum('total'),
        count=Count('id')
    ).order_by('-total')
    
    context = {
        'total_revenue': total_revenue,
        'total_sales': total_sales,
        'average_order_value': average_order_value,
        'revenue_growth': revenue_growth,
        'total_products': total_products,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'total_customers': total_customers,
        'new_customers': new_customers,
        'total_expenses': total_expenses,
        'total_profit': total_profit,
        'daily_sales': daily_sales,
        'sales_by_category': sales_by_category,
        'top_products': top_products,
        'recent_insights': recent_insights,
        'unread_insights': unread_insights,
        'payment_methods': payment_methods,
        'start_date': start_date,
        'end_date': end_date,
    }
    
    return context

# === Sales Analytics ===

@login_required
@business_required
def sales_analytics_view(request):
    """Sales analytics page."""
    business = request.user.business
    
    # Get date range
    period = request.GET.get('period', '30d')
    end_date = timezone.now().date()
    
    if period == '7d':
        start_date = end_date - timedelta(days=7)
    elif period == '30d':
        start_date = end_date - timedelta(days=30)
    elif period == '90d':
        start_date = end_date - timedelta(days=90)
    elif period == '365d':
        start_date = end_date - timedelta(days=365)
    else:
        start_date = end_date - timedelta(days=30)
    
    # Sales data
    sales = Sale.objects.filter(
        business=business,
        sale_date__date__range=[start_date, end_date]
    )
    
    # Daily sales trend
    daily_trend = sales.extra(
        select={'date': "date(sale_date)"}
    ).values('date').annotate(
        total=Sum('total'),
        count=Count('id')
    ).order_by('date')
    
    # Weekly sales trend
    weekly_trend = sales.extra(
        select={'week': "strftime('%Y-%W', sale_date)"}
    ).values('week').annotate(
        total=Sum('total'),
        count=Count('id')
    ).order_by('week')
    
    # Monthly sales trend
    monthly_trend = sales.extra(
        select={'month': "strftime('%Y-%m', sale_date)"}
    ).values('month').annotate(
        total=Sum('total'),
        count=Count('id')
    ).order_by('month')
    
    # Sales by category
    category_sales = SaleItem.objects.filter(
        sale__business=business,
        sale__sale_date__date__range=[start_date, end_date]
    ).values('product__category__name').annotate(
        total_sales=Sum('total'),
        total_quantity=Sum('quantity')
    ).order_by('-total_sales')
    
    # Top products
    top_products = SaleItem.objects.filter(
        sale__business=business,
        sale__sale_date__date__range=[start_date, end_date]
    ).values('product__name', 'product__sku').annotate(
        total_sold=Sum('quantity'),
        total_revenue=Sum('total')
    ).order_by('-total_revenue')[:20]
    
    # Payment methods
    payment_methods = sales.values('payment_method').annotate(
        total=Sum('total'),
        count=Count('id')
    ).order_by('-total')
    
    # Hourly sales (for POS insights)
    hourly_sales = sales.extra(
        select={'hour': "strftime('%H', sale_date)"}
    ).values('hour').annotate(
        total=Sum('total'),
        count=Count('id')
    ).order_by('hour')
    
    # Summary stats
    stats = {
        'total_revenue': sales.aggregate(total=Sum('total'))['total'] or 0,
        'total_sales': sales.count(),
        'average_order': sales.aggregate(avg=Avg('total'))['avg'] or 0,
        'max_order': sales.aggregate(max=Max('total'))['max'] or 0,
        'min_order': sales.aggregate(min=Min('total'))['min'] or 0,
        'unique_customers': sales.values('customer').distinct().count(),
        'total_items_sold': SaleItem.objects.filter(
            sale__business=business,
            sale__sale_date__date__range=[start_date, end_date]
        ).aggregate(total=Sum('quantity'))['total'] or 0,
    }
    
    context = {
        'stats': stats,
        'period': period,
        'start_date': start_date,
        'end_date': end_date,
        'daily_trend': daily_trend,
        'daily_trend_labels_json': json.dumps([
            item['date'] for item in daily_trend[:20]
        ]),
        'daily_trend_totals_json': json.dumps([
            float(item['total']) for item in daily_trend[:20]
        ]),
        'weekly_trend': weekly_trend,
        'monthly_trend': monthly_trend,
        'category_sales': category_sales,
        'category_sales_labels_json': json.dumps([
            item['product__category__name'] or 'Uncategorized'
            for item in category_sales[:8]
        ]),
        'category_sales_totals_json': json.dumps([
            float(item['total_sales']) for item in category_sales[:8]
        ]),
        'top_products': top_products,
        'payment_methods': payment_methods,
        'hourly_sales': hourly_sales,
        'title': 'Sales Analytics'
    }
    
    return render(request, 'analytics/sales.html', context)

# === Product Analytics ===

@login_required
@business_required
def product_analytics_view(request):
    """Product performance analytics."""
    business = request.user.business
    
    # Get top products by revenue
    top_by_revenue = SaleItem.objects.filter(
        sale__business=business
    ).values('product__name', 'product__sku', 'product__id').annotate(
        total_revenue=Sum('total'),
        total_sold=Sum('quantity'),
        total_orders=Count('sale')
    ).order_by('-total_revenue')[:20]
    
    # Get top products by quantity
    top_by_quantity = SaleItem.objects.filter(
        sale__business=business
    ).values('product__name', 'product__sku', 'product__id').annotate(
        total_sold=Sum('quantity'),
        total_revenue=Sum('total')
    ).order_by('-total_sold')[:20]
    
    # Slow moving products (sold less than 5 times in 90 days)
    ninety_days_ago = timezone.now() - timedelta(days=90)
    active_products = Product.objects.filter(
        business=business,
        is_active=True
    )
    
    slow_moving = []
    for product in active_products:
        sales_count = SaleItem.objects.filter(
            product=product,
            sale__sale_date__gte=ninety_days_ago
        ).aggregate(total=Sum('quantity'))['total'] or 0
        
        if sales_count < 5 and product.current_stock > 0:
            slow_moving.append({
                'name': product.name,
                'sku': product.sku,
                'current_stock': product.current_stock,
                'total_sold_90d': sales_count
            })
    
    # Category performance
    category_performance = Category.objects.filter(
        business=business
    ).annotate(
        total_revenue=Sum('products__sale_items__total'),
        total_sold=Sum('products__sale_items__quantity'),
        product_count=Count('products')
    ).order_by('-total_revenue')
    
    # Inventory turnover (last 30 days)
    month_ago = timezone.now() - timedelta(days=30)
    inventory_turnover = SaleItem.objects.filter(
        sale__business=business,
        sale__sale_date__gte=month_ago
    ).values('product__name').annotate(
        sold=Sum('quantity'),
        current_stock=F('product__current_stock')
    ).order_by('-sold')[:20]
    
    context = {
        'top_by_revenue': top_by_revenue,
        'top_by_quantity': top_by_quantity,
        'slow_moving': slow_moving[:20],
        'category_performance': category_performance,
        'inventory_turnover': inventory_turnover,
        'title': 'Product Analytics'
    }
    
    return render(request, 'analytics/products.html', context)

# === Customer Analytics ===

@login_required
@business_required
def customer_analytics_view(request):
    """Customer analytics page."""
    business = request.user.business
    
    # Customer stats
    total_customers = Customer.objects.filter(business=business, is_active=True).count()
    
    # Customer lifetime value (top customers)
    top_customers = Customer.objects.filter(
        business=business,
        sales__isnull=False
    ).annotate(
        total_spent=Sum('sales__total'),
        total_orders=Count('sales'),
        avg_order=Avg('sales__total'),
        last_order=Max('sales__sale_date')
    ).order_by('-total_spent')[:20]
    
    # Customer segments (by spending)
    segments = {
        'VIP': top_customers.filter(total_spent__gte=50000),
        'Regular': top_customers.filter(total_spent__gte=10000, total_spent__lt=50000),
        'Occasional': top_customers.filter(total_spent__gte=1000, total_spent__lt=10000),
    }
    
    # New vs returning customers
    month_ago = timezone.now() - timedelta(days=30)
    new_customers = Customer.objects.filter(
        business=business,
        created_at__gte=month_ago
    ).count()
    
    returning_customers = Sale.objects.filter(
        business=business,
        sale_date__gte=month_ago
    ).values('customer').distinct().count() - new_customers
    
    # Customer retention (90 days)
    ninety_days_ago = timezone.now() - timedelta(days=90)
    customers_90d = Customer.objects.filter(
        business=business,
        created_at__lte=ninety_days_ago
    )
    
    active_customers = Sale.objects.filter(
        business=business,
        customer__in=customers_90d,
        sale_date__gte=ninety_days_ago
    ).values('customer').distinct().count()
    
    retention_rate = (active_customers / customers_90d.count() * 100) if customers_90d.count() > 0 else 0
    
    # Customer growth trend (last 6 months)
    six_months_ago = timezone.now() - timedelta(days=180)
    growth_trend = Customer.objects.filter(
        business=business,
        created_at__gte=six_months_ago
    ).extra(
        select={'month': "strftime('%Y-%m', created_at)"}
    ).values('month').annotate(
        count=Count('id')
    ).order_by('month')
    
    context = {
        'total_customers': total_customers,
        'top_customers': top_customers,
        'segments': segments,
        'new_customers': new_customers,
        'returning_customers': returning_customers,
        'retention_rate': retention_rate,
        'growth_trend': growth_trend,
        'title': 'Customer Analytics'
    }
    
    return render(request, 'analytics/customers.html', context)

# === Financial Analytics ===

@login_required
@business_required
def financial_analytics_view(request):
    """Financial analytics page."""
    business = request.user.business
    
    # Get date range
    period = request.GET.get('period', '30d')
    end_date = timezone.now().date()
    
    if period == '7d':
        start_date = end_date - timedelta(days=7)
    elif period == '30d':
        start_date = end_date - timedelta(days=30)
    elif period == '90d':
        start_date = end_date - timedelta(days=90)
    elif period == '365d':
        start_date = end_date - timedelta(days=365)
    else:
        start_date = end_date - timedelta(days=30)
    
    # Revenue data
    sales = Sale.objects.filter(
        business=business,
        sale_date__date__range=[start_date, end_date]
    )
    total_revenue = sales.aggregate(total=Sum('total'))['total'] or 0
    
    # Expense data
    expenses = Expense.objects.filter(
        business=business,
        expense_date__range=[start_date, end_date]
    )
    total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or 0
    
    # Profit
    total_profit = total_revenue - total_expenses
    profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
    
    # Revenue vs expenses trend
    daily_financial = []
    current_date = start_date
    while current_date <= end_date:
        day_revenue = sales.filter(sale_date__date=current_date).aggregate(
            total=Sum('total')
        )['total'] or 0
        
        day_expenses = expenses.filter(expense_date=current_date).aggregate(
            total=Sum('amount')
        )['total'] or 0
        
        daily_financial.append({
            'date': current_date,
            'revenue': float(day_revenue),
            'expenses': float(day_expenses),
            'profit': float(day_revenue - day_expenses)
        })
        current_date += timedelta(days=1)
    
    # Expense breakdown by category
    expense_by_category = expenses.values('category__name').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')
    
    # Monthly summary
    monthly_summary = []
    current = start_date.replace(day=1)
    while current <= end_date:
        month_end = (current.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        
        month_revenue = sales.filter(sale_date__date__range=[current, month_end]).aggregate(
            total=Sum('total')
        )['total'] or 0
        
        month_expenses = expenses.filter(expense_date__range=[current, month_end]).aggregate(
            total=Sum('amount')
        )['total'] or 0
        
        monthly_summary.append({
            'month': current.strftime('%B %Y'),
            'revenue': float(month_revenue),
            'expenses': float(month_expenses),
            'profit': float(month_revenue - month_expenses)
        })
        
        current = month_end + timedelta(days=1)
    
    # Key financial metrics
    metrics = {
        'total_revenue': total_revenue,
        'total_expenses': total_expenses,
        'total_profit': total_profit,
        'profit_margin': profit_margin,
        'average_daily_revenue': total_revenue / ((end_date - start_date).days + 1) if (end_date - start_date).days > 0 else 0,
        'average_daily_expense': total_expenses / ((end_date - start_date).days + 1) if (end_date - start_date).days > 0 else 0,
        'revenue_growth': calculate_growth(business, start_date, end_date, 'revenue'),
        'expense_growth': calculate_growth(business, start_date, end_date, 'expense'),
    }
    
    context = {
        'metrics': metrics,
        'daily_financial': daily_financial,
        'daily_financial_labels_json': json.dumps([
            item['date'].isoformat() for item in daily_financial
        ]),
        'daily_revenue_json': json.dumps([
            item['revenue'] for item in daily_financial
        ]),
        'daily_expenses_json': json.dumps([
            item['expenses'] for item in daily_financial
        ]),
        'daily_profit_json': json.dumps([
            item['profit'] for item in daily_financial
        ]),
        'expense_by_category': expense_by_category,
        'expense_category_labels_json': json.dumps([
            item['category__name'] or 'Uncategorized'
            for item in expense_by_category[:8]
        ]),
        'expense_category_totals_json': json.dumps([
            float(item['total']) for item in expense_by_category[:8]
        ]),
        'monthly_summary': monthly_summary,
        'period': period,
        'title': 'Financial Analytics'
    }
    
    return render(request, 'analytics/financial.html', context)

def calculate_growth(business, start_date, end_date, metric_type):
    """Calculate growth percentage."""
    days_diff = (end_date - start_date).days + 1
    mid_point = start_date + timedelta(days=days_diff // 2)
    
    if metric_type == 'revenue':
        first_half = Sale.objects.filter(
            business=business,
            sale_date__date__range=[start_date, mid_point]
        ).aggregate(total=Sum('total'))['total'] or 0
        
        second_half = Sale.objects.filter(
            business=business,
            sale_date__date__range=[mid_point + timedelta(days=1), end_date]
        ).aggregate(total=Sum('total'))['total'] or 0
    else:
        first_half = Expense.objects.filter(
            business=business,
            expense_date__range=[start_date, mid_point]
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        second_half = Expense.objects.filter(
            business=business,
            expense_date__range=[mid_point + timedelta(days=1), end_date]
        ).aggregate(total=Sum('amount'))['total'] or 0
    
    if first_half > 0:
        return ((second_half - first_half) / first_half) * 100
    return 0

# === Insights Generation ===

@login_required
@business_required
def generate_insights_view(request):
    """Generate AI-powered business insights."""
    business = request.user.business
    insights_generated = len(run_intelligence_pipeline(business))
    
    messages.success(request, f'Generated {insights_generated} new insights!')
    return redirect('analytics:dashboard')

def generate_sales_insights(business):
    """Generate sales-related insights."""
    insights = []
    thirty_days_ago = timezone.now() - timedelta(days=30)
    
    # Check sales trend
    sales = Sale.objects.filter(
        business=business,
        sale_date__gte=thirty_days_ago
    )
    
    if sales.count() > 0:
        total_revenue = sales.aggregate(total=Sum('total'))['total'] or 0
        
        # Compare with previous period
        prev_start = thirty_days_ago - timedelta(days=30)
        prev_sales = Sale.objects.filter(
            business=business,
            sale_date__range=[prev_start, thirty_days_ago - timedelta(days=1)]
        )
        prev_revenue = prev_sales.aggregate(total=Sum('total'))['total'] or 0
        
        if prev_revenue > 0:
            growth = ((total_revenue - prev_revenue) / prev_revenue) * 100
            
            if growth > 20:
                insight = BusinessInsight.objects.create(
                    business=business,
                    insight_type='TREND',
                    severity='SUCCESS',
                    title='Sales are growing strongly!',
                    description=f'Your sales have increased by {growth:.1f}% compared to the previous period.',
                    recommendation='Continue with your current strategies and consider expanding your product range.',
                    metric='Revenue Growth',
                    current_value=total_revenue,
                    previous_value=prev_revenue,
                    change_percentage=growth,
                    time_period='Last 30 days'
                )
                insights.append(insight)
            elif growth < -20:
                insight = BusinessInsight.objects.create(
                    business=business,
                    insight_type='TREND',
                    severity='WARNING',
                    title='Sales are declining',
                    description=f'Your sales have decreased by {abs(growth):.1f}% compared to the previous period.',
                    recommendation='Review your pricing, promotions, and marketing strategies. Consider running a promotion to boost sales.',
                    metric='Revenue Growth',
                    current_value=total_revenue,
                    previous_value=prev_revenue,
                    change_percentage=growth,
                    time_period='Last 30 days'
                )
                insights.append(insight)
    
    return len(insights)

def generate_product_insights(business):
    """Generate product-related insights."""
    insights = []
    
    # Top selling products
    top_product = SaleItem.objects.filter(
        sale__business=business
    ).values('product__name').annotate(
        total_sold=Sum('quantity')
    ).order_by('-total_sold').first()
    
    if top_product:
        insight = BusinessInsight.objects.create(
            business=business,
            insight_type='OPPORTUNITY',
            severity='SUCCESS',
            title=f'Best Selling Product: {top_product["product__name"]}',
            description=f'This product is your top seller with {top_product["total_sold"]} units sold.',
            recommendation='Consider promoting this product more and ensuring you have adequate stock.',
            metric='Top Product',
            time_period='All time'
        )
        insights.append(insight)
    
    # Slow moving products
    ninety_days_ago = timezone.now() - timedelta(days=90)
    slow_products = Product.objects.filter(
        business=business,
        is_active=True,
        current_stock__gt=0
    ).exclude(
        sale_items__sale__sale_date__gte=ninety_days_ago
    )
    
    if slow_products.count() > 0:
        insight = BusinessInsight.objects.create(
            business=business,
            insight_type='WARNING',
            severity='WARNING',
            title=f'{slow_products.count()} products are slow moving',
            description=f'{slow_products.count()} products have not been sold in the last 90 days.',
            recommendation='Review these products and consider running promotions, bundling, or marking them down to clear stock.',
            metric='Slow Moving Products',
            time_period='Last 90 days'
        )
        insights.append(insight)
    
    return len(insights)

def generate_financial_insights(business):
    """Generate financial insights."""
    insights = []
    thirty_days_ago = timezone.now() - timedelta(days=30)
    
    # Revenue vs expenses
    revenue = Sale.objects.filter(
        business=business,
        sale_date__gte=thirty_days_ago
    ).aggregate(total=Sum('total'))['total'] or 0
    
    expenses = Expense.objects.filter(
        business=business,
        expense_date__gte=thirty_days_ago
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    if revenue > 0:
        profit_margin = ((revenue - expenses) / revenue) * 100
        
        if profit_margin < 10:
            insight = BusinessInsight.objects.create(
                business=business,
                insight_type='RISK',
                severity='CRITICAL',
                title='Low profit margin detected',
                description=f'Your profit margin is {profit_margin:.1f}% which is below the recommended threshold.',
                recommendation='Review your pricing strategy, reduce costs, or look for ways to increase sales volume.',
                metric='Profit Margin',
                current_value=profit_margin,
                time_period='Last 30 days'
            )
            insights.append(insight)
        elif profit_margin > 40:
            insight = BusinessInsight.objects.create(
                business=business,
                insight_type='OPPORTUNITY',
                severity='SUCCESS',
                title='Excellent profit margin!',
                description=f'Your profit margin of {profit_margin:.1f}% is very healthy.',
                recommendation='This is a good position to reinvest in your business or expand operations.',
                metric='Profit Margin',
                current_value=profit_margin,
                time_period='Last 30 days'
            )
            insights.append(insight)
    
    return len(insights)

def generate_customer_insights(business):
    """Generate customer insights."""
    insights = []
    thirty_days_ago = timezone.now() - timedelta(days=30)
    
    # New customers
    new_customers = Customer.objects.filter(
        business=business,
        created_at__gte=thirty_days_ago
    ).count()
    
    if new_customers > 0:
        insight = BusinessInsight.objects.create(
            business=business,
            insight_type='TREND',
            severity='SUCCESS',
            title=f'{new_customers} new customers in the last 30 days',
            description='Your business is attracting new customers.',
            recommendation='Focus on retaining these new customers with follow-up communications and loyalty programs.',
            metric='New Customers',
            time_period='Last 30 days'
        )
        insights.append(insight)
    
    # Customer retention
    ninety_days_ago = timezone.now() - timedelta(days=90)
    returning_customers = Sale.objects.filter(
        business=business,
        sale_date__gte=ninety_days_ago
    ).values('customer').distinct()
    
    if returning_customers.count() > 0:
        insight = BusinessInsight.objects.create(
            business=business,
            insight_type='TREND',
            severity='INFO',
            title=f'{returning_customers.count()} returning customers',
            description='You have a loyal customer base that keeps coming back.',
            recommendation='Consider implementing a customer loyalty program to encourage repeat business.',
            metric='Returning Customers',
            time_period='Last 90 days'
        )
        insights.append(insight)
    
    return len(insights)

def generate_inventory_insights(business):
    """Generate inventory insights."""
    insights = []
    
    # Low stock items
    low_stock = Product.objects.filter(
        business=business,
        current_stock__lte=models.F('reorder_level'),
        current_stock__gt=0,
        is_active=True
    )
    
    if low_stock.count() > 0:
        insight = BusinessInsight.objects.create(
            business=business,
            insight_type='RISK',
            severity='CRITICAL',
            title=f'{low_stock.count()} products are running low',
            description=f'{low_stock.count()} products have stock below their reorder level.',
            recommendation='Review your inventory and reorder these products before they run out.',
            metric='Low Stock Items',
            time_period='Current'
        )
        insights.append(insight)
    
    # Out of stock
    out_of_stock = Product.objects.filter(
        business=business,
        current_stock=0,
        is_active=True
    )
    
    if out_of_stock.count() > 0:
        insight = BusinessInsight.objects.create(
            business=business,
            insight_type='RISK',
            severity='CRITICAL',
            title=f'{out_of_stock.count()} products are out of stock',
            description=f'{out_of_stock.count()} products are currently out of stock.',
            recommendation='Urgently reorder these products to avoid losing sales.',
            metric='Out of Stock Items',
            time_period='Current'
        )
        insights.append(insight)
    
    return len(insights)

# === API Endpoints ===

@login_required
@business_required
def get_dashboard_data_api(request):
    """Get dashboard data as JSON."""
    business = request.user.business
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=30)
    
    data = get_dashboard_data(business, start_date, end_date)
    
    # Convert Decimal to float for JSON
    for key in ['total_revenue', 'average_order_value', 'revenue_growth', 
                'total_expenses', 'total_profit']:
        if key in data:
            data[key] = float(data[key])
    
    # Convert querysets to lists
    data['daily_sales'] = list(data['daily_sales'])
    data['sales_by_category'] = list(data['sales_by_category'])
    data['top_products'] = list(data['top_products'])
    data['payment_methods'] = list(data['payment_methods'])
    
    return JsonResponse(data)

@login_required
@business_required
def mark_insight_read(request, insight_id):
    """Mark an insight as read."""
    insight = get_object_or_404(
        BusinessInsight,
        id=insight_id,
        business=request.user.business
    )
    insight.is_read = True
    insight.read_at = timezone.now()
    insight.save()
    
    return JsonResponse({'success': True})

@login_required
@business_required
@require_POST
def dismiss_insight(request, insight_id):
    """Dismiss an insight."""
    insight = get_object_or_404(
        BusinessInsight,
        id=insight_id,
        business=request.user.business
    )
    insight.is_dismissed = True
    insight.save()
    
    return JsonResponse({'success': True})

@login_required
@business_required
@require_POST
def action_insight(request, insight_id):
    """Mark an insight as actioned."""
    insight = get_object_or_404(
        BusinessInsight,
        id=insight_id,
        business=request.user.business
    )
    insight.is_actioned = True
    insight.actioned_at = timezone.now()
    insight.save()
    
    return JsonResponse({'success': True})