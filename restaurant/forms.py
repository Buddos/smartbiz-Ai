from django import forms
from products.models import Product

from .models import (
    RestaurantCashMovement,
    RestaurantReservation,
    RestaurantSupplier,
    RestaurantTable,
)


class RestaurantTableForm(forms.ModelForm):
    class Meta:
        model = RestaurantTable
        fields = ["number", "zone", "seats"]
        widgets = {
            "number": forms.TextInput(attrs={"class": "input-field", "placeholder": "e.g. 12"}),
            "zone": forms.TextInput(attrs={"class": "input-field", "placeholder": "Indoor"}),
            "seats": forms.NumberInput(attrs={"class": "input-field", "min": 1}),
        }


class RestaurantReservationForm(forms.ModelForm):
    class Meta:
        model = RestaurantReservation
        fields = ["customer_name", "phone", "starts_at", "party_size", "table", "deposit", "notes"]
        widgets = {
            "customer_name": forms.TextInput(attrs={"class": "input-field"}),
            "phone": forms.TextInput(attrs={"class": "input-field", "autocomplete": "tel"}),
            "starts_at": forms.DateTimeInput(attrs={"class": "input-field", "type": "datetime-local"}),
            "party_size": forms.NumberInput(attrs={"class": "input-field", "min": 1}),
            "table": forms.Select(attrs={"class": "input-field"}),
            "deposit": forms.NumberInput(attrs={"class": "input-field", "min": 0, "step": "0.01"}),
            "notes": forms.Textarea(attrs={"class": "input-field", "rows": 3}),
        }

    def __init__(self, *args, business, **kwargs):
        super().__init__(*args, **kwargs)
        self.business = business
        self.fields["table"].queryset = RestaurantTable.objects.filter(
            business=business
        ).exclude(status="BLOCKED")
        self.fields["table"].required = False

    def clean_starts_at(self):
        from django.utils import timezone

        starts_at = self.cleaned_data["starts_at"]
        if starts_at <= timezone.now():
            raise forms.ValidationError("Choose a reservation time in the future.")
        return starts_at

    def clean(self):
        cleaned = super().clean()
        table = cleaned.get("table")
        party_size = cleaned.get("party_size")
        starts_at = cleaned.get("starts_at")
        if table and table.business_id != self.business.id:
            self.add_error("table", "Choose a table belonging to this restaurant.")
        elif table and party_size and party_size > table.seats:
            self.add_error("party_size", "The selected table does not have enough seats.")
        elif table and starts_at:
            conflicting = RestaurantReservation.objects.filter(
                business=self.business,
                table=table,
                starts_at=starts_at,
                status__in=["PENDING", "CONFIRMED"],
            )
            if self.instance.pk:
                conflicting = conflicting.exclude(pk=self.instance.pk)
            if conflicting.exists():
                self.add_error("table", "That table already has a reservation at this time.")
        return cleaned


class RestaurantSupplierForm(forms.ModelForm):
    class Meta:
        model = RestaurantSupplier
        fields = ["name", "contact_name", "phone", "email", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input-field"}),
            "contact_name": forms.TextInput(attrs={"class": "input-field"}),
            "phone": forms.TextInput(attrs={"class": "input-field"}),
            "email": forms.EmailInput(attrs={"class": "input-field"}),
            "notes": forms.Textarea(attrs={"class": "input-field", "rows": 2}),
        }


class RestaurantCashMovementForm(forms.ModelForm):
    class Meta:
        model = RestaurantCashMovement
        fields = ["movement_type", "amount", "reason"]
        widgets = {
            "movement_type": forms.Select(attrs={"class": "input-field"}),
            "amount": forms.NumberInput(attrs={"class": "input-field", "min": "0.01", "step": "0.01"}),
            "reason": forms.TextInput(attrs={"class": "input-field"}),
        }


class RestaurantCashOpenForm(forms.Form):
    opening_cash = forms.DecimalField(
        min_value=0,
        decimal_places=2,
        max_digits=12,
        widget=forms.NumberInput(attrs={"class": "input-field", "min": 0, "step": "0.01"}),
    )


class RestaurantPurchaseOrderForm(forms.Form):
    expected_at = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "input-field", "type": "date"}),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "input-field", "rows": 2}),
    )


class RestaurantCashCloseForm(forms.Form):
    closing_cash = forms.DecimalField(
        min_value=0,
        decimal_places=2,
        max_digits=12,
        widget=forms.NumberInput(attrs={"class": "input-field", "min": 0, "step": "0.01"}),
    )


def restaurant_products(business):
    return Product.objects.filter(business=business, is_active=True).order_by("name")
