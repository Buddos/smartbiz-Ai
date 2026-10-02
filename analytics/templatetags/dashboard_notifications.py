from django import template
from django.urls import reverse

from analytics.models import BusinessInsight
from inventory.models import InventoryAlert


register = template.Library()


@register.inclusion_tag("partials/_dashboard_notifications.html", takes_context=True)
def dashboard_notifications(context):
    request = context.get("request")
    user = getattr(request, "user", None)
    business = getattr(user, "business", None)
    if not user or not user.is_authenticated or not business:
        return {
            "items": [],
            "unread_count": 0,
            "can_view_inventory_alerts": False,
            "can_view_ai_insights": False,
        }

    can_view_inventory_alerts = user.is_superuser or user.has_permission("manage_inventory")
    can_view_ai_insights = user.is_superuser or user.has_permission("view_ai_insights")
    unread_insights = BusinessInsight.objects.filter(
        business=business,
        is_read=False,
        is_dismissed=False,
    )
    active_alerts = InventoryAlert.objects.filter(business=business, status="ACTIVE")
    insight_url = f"{reverse('ai_engine:home')}#insights" if can_view_ai_insights else None
    alert_url = reverse("inventory:alerts") if can_view_inventory_alerts else None
    items = [
        {
            "title": insight.title,
            "message": insight.description,
            "timestamp": insight.generated_at,
            "icon": "fa-lightbulb",
            "url": insight_url,
        }
        for insight in unread_insights.order_by("-generated_at")[:5]
    ]
    items.extend(
        {
            "title": alert.product.name,
            "message": alert.message,
            "timestamp": alert.created_at,
            "icon": "fa-triangle-exclamation",
            "url": alert_url,
        }
        for alert in active_alerts.select_related("product").order_by("-created_at")[:5]
    )
    items.sort(key=lambda item: item["timestamp"], reverse=True)

    return {
        "items": items[:5],
        "unread_count": unread_insights.count() + active_alerts.count(),
        "can_view_inventory_alerts": can_view_inventory_alerts,
        "can_view_ai_insights": can_view_ai_insights,
    }
