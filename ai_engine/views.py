from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from accounts.decorators import business_required, role_required
from .models import AIInsight, AIInsightFeedback, AIRecommendation, ForecastResult
from .services import run_intelligence_pipeline, run_sales_forecast


@login_required
@business_required
@role_required(["OWNER", "MANAGER", "ADMIN", "SUPER_ADMIN"])
def intelligence_home(request):
    business = request.user.business
    insights = AIInsight.objects.filter(
        business=business, status="active",
    ).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
    ).order_by("-score", "-created_at")[:12] if business else []
    recs = AIRecommendation.objects.filter(business=business, status="OPEN").order_by("-created_at")[:12] if business else []
    forecast = ForecastResult.objects.filter(business=business).first() if business else None
    return render(request, "ai_engine/home.html", {
        "insights": insights,
        "recommendations": recs,
        "forecast": forecast,
        "title": "AI Insights",
    })


@login_required
@business_required
@role_required(["OWNER", "MANAGER", "ADMIN", "SUPER_ADMIN"])
@require_POST
def generate_view(request):
    if not request.user.business:
        messages.warning(request, "Set up a business before generating insights.")
        return redirect("businesses:setup")
    created = run_intelligence_pipeline(request.user.business)
    if created:
        messages.success(request, f"Generated {len(created)} new data-based business insights.")
    else:
        messages.info(
            request,
            "Your AI insights are up to date. New insights appear when business data changes.",
        )
    return redirect("ai_engine:home")


@login_required
@business_required
@role_required(["OWNER", "MANAGER", "ADMIN", "SUPER_ADMIN"])
@require_POST
def forecast_view(request):
    if not request.user.business:
        messages.warning(request, "Set up a business before generating a forecast.")
        return redirect("businesses:setup")
    run_sales_forecast(request.user.business)
    messages.success(request, "A sales forecast was generated. Treat it as an estimate, not a guarantee.")
    return redirect("ai_engine:home")


@login_required
@business_required
@role_required(["OWNER", "MANAGER", "ADMIN", "SUPER_ADMIN"])
@never_cache
@require_GET
def assistant_view(request):
    return render(request, "ai_engine/assistant.html", {"title": "AI Assistant"})


@login_required
@business_required
@require_POST
def recommendation_status(request, rec_id, status):
    rec = get_object_or_404(AIRecommendation, id=rec_id, business=request.user.business)
    if status in dict(AIRecommendation.STATUS):
        rec.status = status
        rec.save(update_fields=["status", "updated_at"])
        messages.success(request, "Recommendation updated.")
    return redirect("ai_engine:home")


@login_required
@business_required
@require_POST
def insight_feedback_view(request, insight_id, action):
    insight = get_object_or_404(AIInsight, id=insight_id, business=request.user.business)
    if action not in {"ACCEPTED", "DISMISSED", "EDITED"}:
        return redirect("ai_engine:home")
    AIInsightFeedback.objects.create(
        insight=insight,
        business=request.user.business,
        user=request.user,
        action=action,
        model_version=insight.source_model,
        note=request.POST.get("note", ""),
    )
    insight.mark_feedback("actioned" if action == "ACCEPTED" else "dismissed" if action == "DISMISSED" else "active")
    messages.success(request, "Insight feedback recorded.")
    return redirect("ai_engine:home")
