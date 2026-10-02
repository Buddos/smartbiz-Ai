from django import forms
from django.forms import BaseFormSet, formset_factory

from products.models import Product

from .models import CashDrawerPayout, RetailPurchaseOrder, RetailSupplier


INPUT_CLASS = "input-field"


class RetailSupplierForm(forms.ModelForm):
    class Meta:
        model = RetailSupplier
        fields = ["name", "phone", "email", "lead_time_days", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "phone": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "email": forms.EmailInput(attrs={"class": INPUT_CLASS}),
            "lead_time_days": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 0}),
            "notes": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 2}),
        }


class RetailPurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = RetailPurchaseOrder
        fields = ["supplier", "expected_date", "notes"]
        widgets = {
            "supplier": forms.Select(attrs={"class": INPUT_CLASS}),
            "expected_date": forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}),
            "notes": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 2}),
        }

    def __init__(self, *args, business, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supplier"].queryset = RetailSupplier.objects.filter(
            business=business, is_active=True
        )


class RetailPurchaseOrderItemForm(forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.none(),
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 1}),
    )
    unit_cost = forms.DecimalField(
        min_value=0,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 0, "step": "0.01"}),
    )

    def __init__(self, *args, business, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(
            business=business, is_active=True
        ).order_by("name")


class BaseRetailPurchaseOrderItemFormSet(BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        populated = [
            form.cleaned_data
            for form in self.forms
            if form.cleaned_data
            and form.cleaned_data.get("product")
            and not form.cleaned_data.get("DELETE")
        ]
        if not populated:
            raise forms.ValidationError("Add at least one product to the purchase order.")
        product_ids = [row["product"].id for row in populated]
        if len(product_ids) != len(set(product_ids)):
            raise forms.ValidationError("Each product can only appear once per purchase order.")


RetailPurchaseOrderItemFormSet = formset_factory(
    RetailPurchaseOrderItemForm,
    formset=BaseRetailPurchaseOrderItemFormSet,
    extra=1,
    can_delete=True,
    max_num=20,
    validate_max=True,
)


class DrawerOpenForm(forms.Form):
    opening_balance = forms.DecimalField(
        min_value=0,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 0, "step": "0.01"}),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 2}),
    )


class DrawerCloseForm(forms.Form):
    counted_balance = forms.DecimalField(
        min_value=0,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 0, "step": "0.01"}),
    )
    variance_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 2}),
    )


class CashDrawerPayoutForm(forms.ModelForm):
    class Meta:
        model = CashDrawerPayout
        fields = ["payout_type", "description", "recipient", "amount"]
        widgets = {
            "payout_type": forms.Select(attrs={"class": INPUT_CLASS}),
            "description": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "recipient": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "amount": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 0.01, "step": "0.01"}),
        }
