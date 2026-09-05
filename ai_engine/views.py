from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import business_required, role_required
from .models import AIInsight, AIInsightFeedback, AIQuery, AIRecommendation, ForecastResult
from .services import answer_question, run_intelligence_pipeline, run_sales_forecast


class AssistantForm(forms.Form):
    question = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": "input-field",
            "rows": 3,
            "placeholder": "e.g. Which products should I pay attention to?",
        })
    )


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
    queries = AIQuery.objects.filter(business=business)[:8] if business else []
    form = AssistantForm()
    return render(request, "ai_engine/home.html", {
        "insights": insights,
        "recommendations": recs,
        "forecast": forecast,
        "queries": queries,
        "form": form,
        "has_business": bool(business),
        "title": "AI Decision Support",
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
    messages.success(request, f"Generated {len(created)} ranked insights and recommendations from your business data.")
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
def assistant_view(request):
    if request.method != "POST":
        return redirect("ai_engine:home")
    form = AssistantForm(request.POST)
    if form.is_valid():
        question = form.cleaned_data["question"]
        if not request.user.business:
            messages.info(request, "The assistant uses live data from your business. Set up a business first, then ask your question again.")
            return redirect("ai_engine:home")
        answer = answer_question(request.user.business, question)
        AIQuery.objects.create(
            business=request.user.business,
            user=request.user,
            question=question,
            answer=answer,
        )
    return redirect("ai_engine:home")


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
