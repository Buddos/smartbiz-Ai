from decimal import Decimal

from django import forms
from django.db.models import Q, Sum
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils import timezone

from products.models import Product
from retail.models import RetailSupplier

from .models import (
    ScheduledSupplierPayment,
    SupplierBill,
    SupplierBillLine,
    SupplierPayment,
    WholesalePromotion,
)


INPUT = "input-field"


class WholesalePromotionForm(forms.ModelForm):
    class Meta:
        model = WholesalePromotion
        fields = [
            "name", "promotion_type", "description", "products", "customer_tiers",
            "min_quantity", "min_order_value", "discount_percent", "discount_amount",
            "free_quantity", "max_free_per_order", "max_uses_per_customer",
            "max_total_uses", "weekdays_only", "weekends_only",
            "exclude_existing_discounts", "starts_at", "ends_at", "auto_expire",
            "notify_sms", "notify_email", "notify_in_app",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT}),
            "promotion_type": forms.Select(attrs={"class": INPUT}),
            "description": forms.Textarea(attrs={"class": INPUT, "rows": 3}),
            "products": forms.SelectMultiple(attrs={"class": INPUT, "size": 5}),
            "customer_tiers": forms.TextInput(attrs={
                "class": INPUT, "placeholder": "Tier A, Tier B (leave blank for all)",
            }),
            "min_quantity": forms.NumberInput(attrs={"class": INPUT, "min": 1}),
            "min_order_value": forms.NumberInput(attrs={"class": INPUT, "min": 0, "step": ".01"}),
            "discount_percent": forms.NumberInput(attrs={"class": INPUT, "min": 0, "max": 100, "step": ".01"}),
            "discount_amount": forms.NumberInput(attrs={"class": INPUT, "min": 0, "step": ".01"}),
            "free_quantity": forms.NumberInput(attrs={"class": INPUT, "min": 0}),
            "max_free_per_order": forms.NumberInput(attrs={"class": INPUT, "min": 0}),
            "max_uses_per_customer": forms.NumberInput(attrs={"class": INPUT, "min": 1}),
            "max_total_uses": forms.NumberInput(attrs={"class": INPUT, "min": 1}),
            "starts_at": forms.DateTimeInput(attrs={"class": INPUT, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "ends_at": forms.DateTimeInput(attrs={"class": INPUT, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, business, **kwargs):
        super().__init__(*args, **kwargs)
        existing_products = (
            self.instance.products.values("pk")
            if self.instance.pk else Product.objects.none().values("pk")
        )
        eligible_products = Product.objects.filter(business=business).filter(
            Q(is_active=True) | Q(pk__in=existing_products)
        )
        self.fields["products"].queryset = eligible_products.order_by("name")
        self.fields["products"].required = False
        self.fields["customer_tiers"].help_text = (
            "Comma-separated tiers; set each customer's tier in the customer profile."
        )
        self.fields["ends_at"].required = False
        self.fields["min_order_value"].required = False
        self.fields["discount_percent"].required = False
        self.fields["discount_amount"].required = False
        self.fields["max_uses_per_customer"].required = False
        self.fields["max_total_uses"].required = False
        if self.instance.pk:
            self.initial["starts_at"] = self.instance.starts_at.strftime("%Y-%m-%dT%H:%M")
            if self.instance.ends_at:
                self.initial["ends_at"] = self.instance.ends_at.strftime("%Y-%m-%dT%H:%M")

    def clean(self):
        cleaned = super().clean()
        starts = cleaned.get("starts_at")
        ends = cleaned.get("ends_at")
        if starts and ends and ends <= starts:
            self.add_error("ends_at", "End date and time must be after the start.")
        if cleaned.get("weekdays_only") and cleaned.get("weekends_only"):
            self.add_error("weekends_only", "Choose weekdays or weekends, not both.")
        if cleaned.get("promotion_type") == "BUY_X_GET_Y":
            if not cleaned.get("free_quantity"):
                self.add_error("free_quantity", "Set at least one free unit.")
        elif not (cleaned.get("discount_percent") or cleaned.get("discount_amount")):
            self.add_error("discount_percent", "Set a percentage or fixed discount.")
        return cleaned


class SupplierBillForm(forms.ModelForm):
    class Meta:
        model = SupplierBill
        fields = [
            "supplier", "invoice_number", "invoice_date", "due_date",
            "payment_terms", "amount", "bank_details", "notes", "attachment",
        ]
        widgets = {
            "supplier": forms.Select(attrs={"class": INPUT}),
            "invoice_number": forms.TextInput(attrs={"class": INPUT}),
            "invoice_date": forms.DateInput(attrs={"class": INPUT, "type": "date"}),
            "due_date": forms.DateInput(attrs={"class": INPUT, "type": "date"}),
            "payment_terms": forms.Select(attrs={"class": INPUT}),
            "amount": forms.NumberInput(attrs={"class": INPUT, "min": ".01", "step": ".01"}),
            "bank_details": forms.TextInput(attrs={"class": INPUT}),
            "notes": forms.Textarea(attrs={"class": INPUT, "rows": 3}),
            "attachment": forms.ClearableFileInput(attrs={"class": INPUT}),
        }

    def __init__(self, *args, business, **kwargs):
        super().__init__(*args, **kwargs)
        eligible_suppliers = RetailSupplier.objects.filter(business=business)
        if self.instance.pk:
            eligible_suppliers = eligible_suppliers.filter(
                Q(is_active=True) | Q(pk=self.instance.supplier_id)
            )
        else:
            eligible_suppliers = eligible_suppliers.filter(is_active=True)
        self.fields["supplier"].queryset = eligible_suppliers.order_by("name")
        self.fields["attachment"].required = False

    def clean(self):
        cleaned = super().clean()
        invoice_date = cleaned.get("invoice_date")
        due_date = cleaned.get("due_date")
        amount = cleaned.get("amount")
        if invoice_date and due_date and due_date < invoice_date:
            self.add_error("due_date", "Due date cannot be before the invoice date.")
        if self.instance.pk and amount is not None:
            committed_amount = self.instance.amount_paid + (
                self.instance.scheduled_payments.filter(status="SCHEDULED").aggregate(
                    total=Sum("amount"),
                )["total"] or Decimal("0")
            )
            if amount < committed_amount:
                self.add_error(
                    "amount",
                    "Invoice amount cannot be less than recorded and scheduled payments.",
                )
        return cleaned


class BaseSupplierBillLineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        seen_products = set()
        line_total = 0
        has_line_items = False
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            product = form.cleaned_data.get("product")
            if product and product.pk in seen_products:
                raise forms.ValidationError("Each product can only appear once on an invoice.")
            if product:
                seen_products.add(product.pk)
            quantity = form.cleaned_data.get("quantity")
            unit_cost = form.cleaned_data.get("unit_cost")
            if quantity and unit_cost is not None:
                has_line_items = True
                line_total += quantity * unit_cost
        if has_line_items and line_total != self.instance.amount:
            raise forms.ValidationError(
                "Line item totals must equal the supplier invoice amount."
            )


class SupplierBillLineForm(forms.ModelForm):
    class Meta:
        model = SupplierBillLine
        fields = ["product", "description", "quantity", "unit_cost"]
        widgets = {
            "product": forms.Select(attrs={"class": INPUT}),
            "description": forms.TextInput(attrs={"class": INPUT}),
            "quantity": forms.NumberInput(attrs={"class": INPUT, "min": 1}),
            "unit_cost": forms.NumberInput(attrs={"class": INPUT, "min": 0, "step": ".01"}),
        }

    def __init__(self, *args, business=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].required = False
        self.fields["product"].queryset = Product.objects.filter(
            business=business, is_active=True,
        ).order_by("name") if business else Product.objects.none()


SupplierBillLineFormSet = inlineformset_factory(
    SupplierBill,
    SupplierBillLine,
    formset=BaseSupplierBillLineFormSet,
    form=SupplierBillLineForm,
    extra=1,
    can_delete=True,
)


class SupplierPaymentForm(forms.ModelForm):
    class Meta:
        model = SupplierPayment
        fields = ["amount", "payment_method", "payment_date", "reference", "notes", "proof"]
        widgets = {
            "amount": forms.NumberInput(attrs={"class": INPUT, "min": ".01", "step": ".01"}),
            "payment_method": forms.Select(attrs={"class": INPUT}),
            "payment_date": forms.DateInput(attrs={"class": INPUT, "type": "date"}),
            "reference": forms.TextInput(attrs={"class": INPUT}),
            "notes": forms.Textarea(attrs={"class": INPUT, "rows": 2}),
            "proof": forms.ClearableFileInput(attrs={"class": INPUT}),
        }


class ScheduledPaymentForm(forms.ModelForm):
    class Meta:
        model = ScheduledSupplierPayment
        fields = [
            "amount", "scheduled_date", "payment_method", "notify_user",
            "notify_supplier", "notes",
        ]
        widgets = {
            "amount": forms.NumberInput(attrs={"class": INPUT, "min": ".01", "step": ".01"}),
            "scheduled_date": forms.DateInput(attrs={"class": INPUT, "type": "date"}),
            "payment_method": forms.Select(attrs={"class": INPUT}),
            "notify_user": forms.CheckboxInput(),
            "notify_supplier": forms.CheckboxInput(),
            "notes": forms.Textarea(attrs={"class": INPUT, "rows": 2}),
        }

    def clean_scheduled_date(self):
        scheduled_date = self.cleaned_data["scheduled_date"]
        if scheduled_date < timezone.localdate():
            raise forms.ValidationError("Payment date cannot be in the past.")
        return scheduled_date


class BatchScheduleForm(forms.Form):
    bills = forms.ModelMultipleChoiceField(
        queryset=SupplierBill.objects.none(),
        widget=forms.CheckboxSelectMultiple,
    )
    scheduled_date = forms.DateField(widget=forms.DateInput(attrs={"class": INPUT, "type": "date"}))
    payment_method = forms.ChoiceField(
        choices=SupplierPayment.METHODS,
        widget=forms.Select(attrs={"class": INPUT}),
    )

    def __init__(self, *args, business, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bills"].queryset = SupplierBill.objects.filter(
            business=business, status__in=["OPEN", "PARTIAL"], amount__gt=0,
        ).select_related("supplier").prefetch_related(
            "payments", "scheduled_payments",
        ).order_by("due_date")

        def bill_label(bill):
            scheduled_total = sum(
                (
                    payment.amount for payment in bill.scheduled_payments.all()
                    if payment.status == "SCHEDULED"
                ),
                Decimal("0"),
            )
            available = max(bill.balance - scheduled_total, Decimal("0"))
            return (
                f"{bill.invoice_number} · {bill.supplier.name} · due {bill.due_date:%d %b} · "
                f"{business.currency} {available:,.2f} to schedule"
            )

        self.fields["bills"].label_from_instance = bill_label

    def clean_scheduled_date(self):
        scheduled_date = self.cleaned_data["scheduled_date"]
        if scheduled_date < timezone.localdate():
            raise forms.ValidationError("Payment date cannot be in the past.")
        return scheduled_date
