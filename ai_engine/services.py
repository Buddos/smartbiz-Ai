from datetime import timedelta
from decimal import Decimal
from statistics import mean, pstdev

from django.db import transaction
from django.conf import settings
from django.core.mail import send_mail
from django.db.models import F, Sum, Count
from django.utils import timezone
from sklearn.linear_model import LinearRegression
import numpy as np

from expenses.models import Expense
from inventory.models import InventoryAlert
from products.models import Product
from sales.models import Sale, SaleItem

from .models import AIInsight, AIInsightFeedback, AIRecommendation, FeatureSnapshot, ForecastResult, InsightDelivery


ENGINE_VERSION = "rules.v1"


def _money(value):
    return float(value or 0)


def _score(severity, confidence, recency_penalty=0, duplicate_penalty=0):
    """Apply the documented ranking formula and keep the result in the 0-1 range."""
    value = (0.55 * severity) + (0.45 * confidence) - (0.15 * recency_penalty) - (0.25 * duplicate_penalty)
    return round(max(0.0, min(1.0, value)), 4)


def _severity_label(score):
    if score >= 0.8:
        return "CRITICAL"
    if score >= 0.5:
        return "WARNING"
    return "INFO"


def _delivery_band(score):
    if score >= 0.8:
        return "critical"
    if score >= 0.5:
        return "notable"
    return "background"


def _feedback_penalty(business, dedupe_key):
    """Use recent dismissals as a transparent confidence adjustment."""
    feedback = AIInsightFeedback.objects.filter(
        business=business,
        insight__dedupe_key=dedupe_key,
        created_at__gte=timezone.now() - timedelta(days=30),
    )
    total = feedback.count()
    dismissed = feedback.filter(action="DISMISSED").count()
    return (dismissed / total) if total else 0


def build_feature_snapshots(business, as_of=None):
    """Compute tenant-scoped features once so rules do not repeatedly scan raw tables."""
    as_of = as_of or timezone.now().date()
    start_30 = as_of - timedelta(days=30)
    start_7 = as_of - timedelta(days=7)
    products = Product.objects.filter(business=business, is_active=True)
    snapshots = []
    category_features = {}
    category_rows = SaleItem.objects.filter(
        sale__business=business,
        sale__sale_date__date__gte=start_30,
    ).values("product__category_id").annotate(
        units=Sum("quantity"), revenue=Sum("total"),
    )
    for row in category_rows:
        category_features[str(row["product__category_id"] or "uncategorized")] = {
            "units_sold_30d": int(row["units"] or 0),
            "revenue_30d": _money(row["revenue"]),
        }
    expense_trends = {}
    expense_rows = Expense.objects.filter(
        business=business,
        expense_date__gte=as_of - timedelta(days=60),
    ).values("category__name").annotate(total=Sum("amount"))
    for row in expense_rows:
        expense_trends[row["category__name"] or "Uncategorized"] = _money(row["total"])

    for product in products.iterator():
        sales = SaleItem.objects.filter(
            sale__business=business,
            product=product,
            sale__sale_date__date__gte=start_30,
        ).aggregate(qty_total=Sum("quantity"), revenue_total=Sum("total"))
        recent = SaleItem.objects.filter(
            sale__business=business,
            product=product,
            sale__sale_date__date__gte=start_7,
        ).aggregate(total=Sum("quantity"))
        units_30 = int(sales["qty_total"] or 0)
        units_7 = int(recent["total"] or 0)
        velocity = round(units_30 / 30, 4)
        features = {
            "units_sold_7d": units_7,
            "units_sold_30d": units_30,
            "revenue_30d": _money(sales["revenue_total"]),
            "stock_level": product.current_stock,
            "reorder_level": product.reorder_level,
            "stock_velocity_per_day": velocity,
            "days_of_stock": round(product.current_stock / velocity, 2) if velocity else None,
            "margin_percent": float(product.profit_margin),
            "weekday": as_of.weekday(),
            "category_features": category_features.get(str(product.category_id or "uncategorized"), {}),
            "expense_category_totals_60d": expense_trends,
        }
        snapshot, _ = FeatureSnapshot.objects.update_or_create(
            business=business,
            product=product,
            feature_date=as_of,
            defaults={"features": features, "captured_at": timezone.now()},
        )
        snapshots.append(snapshot)
    return snapshots


def _candidate_insights(business, snapshots, as_of):
    candidates = []
    start_30 = as_of - timedelta(days=30)
    previous_start = as_of - timedelta(days=60)
    previous_end = start_30 - timedelta(days=1)
    current_revenue = Sale.objects.filter(
        business=business, sale_date__date__gte=start_30
    ).aggregate(total=Sum("total"))["total"] or 0
    previous_revenue = Sale.objects.filter(
        business=business, sale_date__date__range=[previous_start, previous_end]
    ).aggregate(total=Sum("total"))["total"] or 0

    if previous_revenue:
        change = float((current_revenue - previous_revenue) / previous_revenue * 100)
        if abs(change) >= 5:
            direction = "increased" if change > 0 else "declined"
            candidates.append({
                "insight_type": "SALES", "insight_kind": "insight", "source": "STAT",
                "source_model": ENGINE_VERSION, "title": f"Sales {direction} compared with the previous period",
                "observation": f"Revenue was KSh {_money(current_revenue):,.2f}, compared with KSh {_money(previous_revenue):,.2f} previously ({change:+.1f}%).",
                "interpretation": "This is an observed trend, not a guarantee. Review the underlying products and transaction volume before acting.",
                "recommendation": "Review recent demand, pricing, and promotions, then monitor the next period.",
                "severity": min(1.0, 0.55 + abs(change) / 100), "confidence": 0.86,
                "related_entity_id": "", "dedupe_key": f"sales-trend:{'up' if change > 0 else 'down'}",
                "metadata": {"current_revenue": _money(current_revenue), "previous_revenue": _money(previous_revenue), "change_pct": change},
            })

    # Transparent anomaly detection: compare the latest complete day with the
    # trailing 30-day daily distribution, avoiding a black-box alert.
    daily = list(
        Sale.objects.filter(business=business, sale_date__date__gte=start_30)
        .extra(select={"day": "date(sale_date)"})
        .values("day")
        .annotate(day_total=Sum("total"))
        .order_by("day")
    )
    values = [_money(row["day_total"]) for row in daily]
    if len(values) >= 5:
        baseline = values[:-1]
        latest = values[-1]
        spread = pstdev(baseline) if len(baseline) > 1 else 0
        if spread and abs(latest - mean(baseline)) >= 2 * spread:
            direction = "above" if latest > mean(baseline) else "below"
            candidates.append({
                "insight_type": "SALES", "insight_kind": "alert", "source": "STAT",
                "source_model": ENGINE_VERSION, "title": f"Unusual daily sales: {direction} normal",
                "observation": f"The latest complete day recorded KSh {latest:,.2f}, compared with a 30-day daily average of KSh {mean(baseline):,.2f}.",
                "interpretation": "This is a statistical alert based on a two-standard-deviation threshold. Check for one-off events before changing strategy.",
                "recommendation": "Review the day’s products, channels, and transactions to understand the unusual movement.",
                "severity": 0.82, "confidence": 0.78, "related_entity_id": "",
                "dedupe_key": "sales-anomaly:latest-day", "metadata": {"latest": latest, "average": mean(baseline), "std_dev": spread},
            })

    for snapshot in snapshots:
        feature = snapshot.features
        stock = feature["stock_level"]
        reorder = feature["reorder_level"]
        days = feature["days_of_stock"]
        product = snapshot.product
        if stock <= reorder:
            severity = 1.0 if stock == 0 else min(0.95, 0.7 + (reorder - stock + 1) / max(reorder + 1, 1) * 0.2)
            candidates.append({
                "insight_type": "INVENTORY", "insight_kind": "alert", "source": "RULE",
                "source_model": ENGINE_VERSION, "title": f"{product.name} needs a stock review",
                "observation": f"Stock is {stock} units against a reorder level of {reorder}; estimated days of stock: {days or 'unknown'}.",
                "interpretation": "Inventory is updated from recorded movements. Treat this as decision support and confirm supplier lead time before ordering.",
                "recommendation": f"Review recent sales and supplier lead time for {product.name} before restocking.",
                "severity": severity, "confidence": 0.94 if stock == 0 else 0.88,
                "related_entity_id": str(product.id), "dedupe_key": f"stock:{product.id}",
                "metadata": feature,
            })
        if feature["units_sold_30d"] == 0 and stock > 0:
            candidates.append({
                "insight_type": "PRODUCT", "insight_kind": "recommendation", "source": "STAT",
                "source_model": ENGINE_VERSION, "title": f"{product.name} is slow-moving",
                "observation": f"No units of {product.name} were recorded in the last 30 days while {stock} remain in stock.",
                "interpretation": "The product may need a demand, pricing, or promotion review before more inventory is purchased.",
                "recommendation": "Review demand and consider a promotion or bundle before increasing stock.",
                "severity": 0.6, "confidence": 0.82, "related_entity_id": str(product.id),
                "dedupe_key": f"slow-moving:{product.id}", "metadata": feature,
            })

    expenses = list(Expense.objects.filter(business=business, expense_date__gte=previous_start).values("expense_date", "amount", "category__name"))
    current_expenses = sum(_money(row["amount"]) for row in expenses if row["expense_date"] >= start_30)
    previous_expenses = sum(_money(row["amount"]) for row in expenses if row["expense_date"] < start_30)
    if previous_expenses and current_expenses > previous_expenses * 1.15:
        change = (current_expenses - previous_expenses) / previous_expenses * 100
        candidates.append({
            "insight_type": "EXPENSE", "insight_kind": "alert", "source": "STAT",
            "source_model": ENGINE_VERSION, "title": "Operating expenses increased",
            "observation": f"Expenses increased to KSh {current_expenses:,.2f} from KSh {previous_expenses:,.2f} ({change:+.1f}%).",
            "interpretation": "The system cannot claim a specific cause from totals alone. Review the largest expense categories.",
            "recommendation": "Compare transport, purchases, rent, and utilities with the previous period.",
            "severity": min(0.95, 0.6 + change / 100), "confidence": 0.8,
            "related_entity_id": "", "dedupe_key": "expense-trend:increase",
            "metadata": {"current_expenses": current_expenses, "previous_expenses": previous_expenses, "change_pct": change},
        })
    return candidates


@transaction.atomic
def run_intelligence_pipeline(business, as_of=None):
    """Run feature engineering, candidate generation, scoring, deduplication, and delivery persistence."""
    as_of = as_of or timezone.now().date()
    snapshots = build_feature_snapshots(business, as_of)
    candidates = _candidate_insights(business, snapshots, as_of)
    created = []
    for candidate in candidates:
        recent = AIInsight.objects.filter(
            business=business, dedupe_key=candidate["dedupe_key"],
            created_at__gte=timezone.now() - timedelta(days=7),
            status="active",
        ).exists()
        feedback_penalty = _feedback_penalty(business, candidate["dedupe_key"])
        score = _score(
            candidate["severity"],
            candidate["confidence"] * (1 - feedback_penalty * 0.5),
            recency_penalty=1 if recent else 0,
            duplicate_penalty=feedback_penalty,
        )
        if recent or score < 0.5:
            continue
        insight = AIInsight.objects.create(
            business=business,
            insight_type=candidate["insight_type"],
            source=candidate["source"],
            title=candidate["title"],
            observation=candidate["observation"],
            interpretation=candidate["interpretation"],
            metadata=candidate["metadata"],
            insight_kind=candidate["insight_kind"],
            source_model=candidate["source_model"],
            severity_score=candidate["severity"],
            confidence=candidate["confidence"],
            score=score,
            related_entity_id=candidate["related_entity_id"],
            dedupe_key=candidate["dedupe_key"],
            status="active",
            delivery_band=_delivery_band(score),
            expires_at=timezone.now() + timedelta(days=7),
        )
        AIRecommendation.objects.create(
            business=business,
            category=candidate["insight_type"].title(),
            title=candidate["title"],
            suggestion=candidate["recommendation"],
            priority="HIGH" if score >= 0.8 else "MEDIUM",
            related_insight=insight,
        )
        InsightDelivery.objects.create(
            insight=insight,
            business=business,
            channel="DASHBOARD",
            status="SENT",
            sent_at=timezone.now(),
        )
        if score >= 0.8:
            critical_today = InsightDelivery.objects.filter(
                business=business,
                channel="EMAIL",
                status="SENT",
                sent_at__date=timezone.now().date(),
            ).count()
            if critical_today < 3 and business.email:
                try:
                    send_mail(
                        f"SmartBiz AI critical alert: {insight.title}",
                        f"{insight.observation}\n\nSuggested action: {candidate['recommendation']}",
                        getattr(settings, "DEFAULT_FROM_EMAIL", None),
                        [business.email],
                    )
                    InsightDelivery.objects.create(
                        insight=insight, business=business, channel="EMAIL",
                        status="SENT", sent_at=timezone.now(),
                    )
                except Exception as exc:
                    InsightDelivery.objects.create(
                        insight=insight, business=business, channel="EMAIL",
                        status="FAILED", error_message=str(exc),
                    )
            else:
                InsightDelivery.objects.create(
                    insight=insight, business=business, channel="EMAIL", status="SKIPPED",
                    error_message="Daily critical email limit reached or business email is missing.",
                )
        created.append(insight)
    return created


def generate_intelligence(business):
    """Rule + stats insights. AI interpretation is labelled separately from observations."""
    created_insights = []
    created_recs = []

    today = timezone.now().date()
    this_start = today - timedelta(days=30)
    prev_start = today - timedelta(days=60)
    prev_end = this_start - timedelta(days=1)

    this_sales = Sale.objects.filter(business=business, sale_date__date__gte=this_start)
    prev_sales = Sale.objects.filter(
        business=business, sale_date__date__range=[prev_start, prev_end]
    )
    this_rev = this_sales.aggregate(t=Sum("total"))["t"] or 0
    prev_rev = prev_sales.aggregate(t=Sum("total"))["t"] or 0

    if prev_rev:
        change = ((this_rev - prev_rev) / prev_rev) * 100
        if change > 5:
            title = "Sales increased compared with the previous period"
            rec_text = "Keep monitoring demand and stock for your strongest sellers."
            severity = "SALES"
        elif change < -5:
            title = "Sales declined compared with the previous period"
            rec_text = "Review recent demand, pricing, or promotion before restocking slow items."
            severity = "SALES"
        else:
            title = "Sales are relatively stable"
            rec_text = "Watch weekly movement and keep recording transactions consistently."
            severity = "SALES"
        insight = AIInsight.objects.create(
            business=business,
            insight_type=severity,
            source="STAT",
            title=title,
            observation=(
                f"Observed data: last 30 days revenue is KSh {_money(this_rev):,.2f} "
                f"versus KSh {_money(prev_rev):,.2f} in the prior 30 days "
                f"({change:+.1f}%)."
            ),
            interpretation=(
                "This is an interpretation of the trend, not a guarantee. "
                "Short windows can move with a few large sales."
            ),
            metadata={"current": _money(this_rev), "previous": _money(prev_rev), "change_pct": float(change)},
        )
        created_insights.append(insight)
        created_recs.append(
            AIRecommendation.objects.create(
                business=business,
                category="Sales",
                title=title,
                suggestion=rec_text,
                priority="HIGH" if abs(change) > 20 else "MEDIUM",
                related_insight=insight,
            )
        )

    top = (
        SaleItem.objects.filter(sale__business=business, sale__sale_date__date__gte=this_start)
        .values("product__name", "product_id")
        .annotate(qty=Sum("quantity"), revenue=Sum("total"))
        .order_by("-revenue")
        .first()
    )
    if top:
        insight = AIInsight.objects.create(
            business=business,
            insight_type="PRODUCT",
            source="STAT",
            title=f"Strongest seller: {top['product__name']}",
            observation=(
                f"Observed data: {top['product__name']} led revenue in the last 30 days "
                f"with {top['qty']} units and KSh {_money(top['revenue']):,.2f}."
            ),
            interpretation="This product currently contributes the most recorded sales value.",
        )
        created_insights.append(insight)
        created_recs.append(
            AIRecommendation.objects.create(
                business=business,
                category="Inventory",
                title=f"Review stock for {top['product__name']}",
                suggestion="Check reorder level against recent sales before the item runs out.",
                priority="HIGH",
                related_insight=insight,
            )
        )

    low_stock = Product.objects.filter(
        business=business, is_active=True, current_stock__lte=F("reorder_level")
    )
    for product in low_stock[:8]:
        insight = AIInsight.objects.create(
            business=business,
            insight_type="INVENTORY",
            source="RULE",
            title=f"{product.name} is approaching its reorder level",
            observation=(
                f"Observed data: {product.name} has {product.current_stock} units "
                f"against a reorder level of {product.reorder_level}."
            ),
            interpretation=(
                "Treat this as decision support, not an automatic purchase instruction. "
                "Review demand before restocking."
            ),
        )
        created_insights.append(insight)
        created_recs.append(
            AIRecommendation.objects.create(
                business=business,
                category="Inventory",
                title=f"Review stock for {product.name}",
                suggestion="Confirm recent sales and supplier lead time, then restock if needed.",
                priority="HIGH" if product.current_stock == 0 else "MEDIUM",
                related_insight=insight,
            )
        )
        InventoryAlert.objects.get_or_create(
            business=business,
            product=product,
            alert_type="OUT_OF_STOCK" if product.current_stock == 0 else "LOW_STOCK",
            status="ACTIVE",
            defaults={
                "severity": "CRITICAL" if product.current_stock == 0 else "WARNING",
                "message": f"{product.name}: {product.current_stock} vs reorder {product.reorder_level}",
                "current_value": product.current_stock,
                "threshold_value": product.reorder_level,
            },
        )

    this_exp = Expense.objects.filter(business=business, expense_date__gte=this_start).aggregate(
        t=Sum("amount")
    )["t"] or 0
    prev_exp = Expense.objects.filter(
        business=business, expense_date__range=[prev_start, prev_end]
    ).aggregate(t=Sum("amount"))["t"] or 0
    if prev_exp and this_exp > prev_exp * Decimal("1.15"):
        insight = AIInsight.objects.create(
            business=business,
            insight_type="EXPENSE",
            source="STAT",
            title="Operating expenses increased compared with the previous period",
            observation=(
                f"Observed data: expenses were KSh {_money(this_exp):,.2f} vs "
                f"KSh {_money(prev_exp):,.2f} previously."
            ),
            interpretation=(
                "The system does not claim a specific cause. Review the largest categories "
                "to see whether the increase is temporary or recurring."
            ),
        )
        created_insights.append(insight)
        created_recs.append(
            AIRecommendation.objects.create(
                business=business,
                category="Expenses",
                title="Review the largest expense categories",
                suggestion="Open expense analytics and compare rent, transport, purchases, and utilities.",
                priority="HIGH",
                related_insight=insight,
            )
        )

    return created_insights, created_recs


def run_sales_forecast(business, horizon_days=7):
    """Simple linear regression on daily sales. Forecasts are estimates, not guarantees."""
    today = timezone.now().date()
    start = today - timedelta(days=90)
    sales = (
        Sale.objects.filter(business=business, sale_date__date__gte=start)
        .extra(select={"day": "date(sale_date)"})
        .values("day")
        .annotate(total=Sum("total"))
        .order_by("day")
    )
    points = list(sales)
    notes = "Forecasts are estimates based on available history, not guarantees."
    if len(points) < 5:
        result = ForecastResult.objects.create(
            business=business,
            metric="sales",
            horizon_days=horizon_days,
            model_name="insufficient_data",
            predicted_value=0,
            series=[],
            notes="Not enough daily sales history yet. Record more transactions, then retry.",
        )
        return result

    y = np.array([float(p["total"] or 0) for p in points], dtype=float)
    x = np.arange(len(y)).reshape(-1, 1)
    model = LinearRegression()
    model.fit(x, y)
    pred = model.predict(np.arange(len(y), len(y) + horizon_days).reshape(-1, 1))
    in_sample = model.predict(x)
    mae = float(np.mean(np.abs(y - in_sample)))
    rmse = float(np.sqrt(np.mean((y - in_sample) ** 2)))
    denom = np.where(y == 0, 1, y)
    mape = float(np.mean(np.abs((y - in_sample) / denom)) * 100)
    series = [
        {"date": str(p["day"]), "actual": float(p["total"] or 0)} for p in points
    ]
    for i, value in enumerate(pred, start=1):
        series.append({"date": str(today + timedelta(days=i)), "forecast": round(float(value), 2)})
    return ForecastResult.objects.create(
        business=business,
        metric="sales",
        horizon_days=horizon_days,
        model_name="LinearRegression",
        predicted_value=round(Decimal(str(max(pred.sum(), 0))), 2),
        mae=mae,
        rmse=rmse,
        mape=mape,
        series=series,
        notes=notes,
    )


def answer_question(business, question):
    q = (question or "").strip().lower()
    today = timezone.now().date()
    month_start = today.replace(day=1)
    month_sales = Sale.objects.filter(business=business, sale_date__date__gte=month_start)
    revenue = month_sales.aggregate(t=Sum("total"))["t"] or 0
    expenses = Expense.objects.filter(business=business, expense_date__gte=month_start).aggregate(
        t=Sum("amount")
    )["t"] or 0

    if any(w in q for w in ["low stock", "reorder", "inventory", "stock"]):
        items = Product.objects.filter(
            business=business, is_active=True, current_stock__lte=F("reorder_level")
        )[:8]
        if not items:
            return "No products are currently at or below their reorder level."
        lines = [f"- {p.name}: {p.current_stock} units (reorder {p.reorder_level})" for p in items]
        return "Products that deserve stock attention:\n" + "\n".join(lines)

    if "expense" in q:
        return (
            f"This month expenses total KSh {_money(expenses):,.2f}. "
            "Open expense analytics to see which categories changed."
        )

    if any(w in q for w in ["top", "best", "sold the most", "products"]):
        top = (
            SaleItem.objects.filter(sale__business=business, sale__sale_date__date__gte=month_start)
            .values("product__name")
            .annotate(qty=Sum("quantity"), revenue=Sum("total"))
            .order_by("-revenue")[:5]
        )
        if not top:
            return "There are no sales this month yet, so there is no top-product ranking."
        lines = [
            f"- {row['product__name']}: {row['qty']} units, KSh {_money(row['revenue']):,.2f}"
            for row in top
        ]
        return "Top products this month:\n" + "\n".join(lines)

    if any(w in q for w in ["why", "changed", "attention", "this week"]):
        recs = AIRecommendation.objects.filter(business=business, status="OPEN")[:5]
        if not recs:
            return (
                f"This month sales are KSh {_money(revenue):,.2f} and expenses are "
                f"KSh {_money(expenses):,.2f}. Generate insights from the AI page for a fuller review."
            )
        lines = [f"- {r.title}: {r.suggestion}" for r in recs]
        return "What deserves attention:\n" + "\n".join(lines)

    return (
        f"This month your recorded sales are KSh {_money(revenue):,.2f} "
        f"across {month_sales.count()} transactions. Expenses are KSh {_money(expenses):,.2f}. "
        "Ask about top products, low stock, expenses, or what deserves attention."
    )
