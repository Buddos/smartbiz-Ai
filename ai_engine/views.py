from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import business_required, role_required
from .models import AIInsight, AIInsightFeedback, AIQuery, AIRecommendation, ForecastResult
from .services import run_sales_forecast
from .gemini import (
    GeminiError,
    answer_business_question,
    generate_ai_engine_review,
)


class AssistantForm(forms.Form):
    question = forms.CharField(
        max_length=1000,
        widget=forms.Textarea(attrs={
            "class": "input-field",
            "rows": 3,
            "maxlength": 1000,
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
    queries = list(AIQuery.objects.filter(business=business)[:8]) if business else []
    queries.reverse()
    form = AssistantForm()
    return render(request, "ai_engine/home.html", {
        "insights": insights,
        "recommendations": recs,
        "forecast": forecast,
        "queries": queries,
        "form": form,
        "has_business": bool(business),
        "gemini_configured": bool(getattr(settings, "GEMINI_API_KEY", "").strip()),
        "gemini_model": getattr(settings, "GEMINI_MODEL", "gemini-3.8-flash"),
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
    try:
        created, review = generate_ai_engine_review(request.user.business)
    except GeminiError as exc:
        messages.error(
            request,
            f"Gemini insight generation failed: {exc}",
        )
    else:
        messages.success(
            request,
            f"Generated {len(created)} data-based alerts and refreshed the Gemini business review: {review.title}",
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
def assistant_view(request):
    if request.method != "POST":
        return redirect(f"{reverse('ai_engine:home')}#assistant")
    form = AssistantForm(request.POST)
    if form.is_valid():
        question = form.cleaned_data["question"]
        if not request.user.business:
            messages.info(request, "The assistant uses live data from your business. Set up a business first, then ask your question again.")
            return redirect("ai_engine:home")
        try:
            answer = answer_business_question(request.user.business, question)
        except GeminiError as exc:
            messages.error(request, f"The Gemini assistant could not answer: {exc}")
            return redirect(f"{reverse('ai_engine:home')}#assistant")
        AIQuery.objects.create(
            business=request.user.business,
            user=request.user,
            question=question,
            answer=answer,
        )
    else:
        messages.error(request, "Enter a question of up to 1,000 characters.")
    return redirect(f"{reverse('ai_engine:home')}#assistant")


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
