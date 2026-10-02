from datetime import timedelta

from django import forms
from django.db.models import F, Q
from django.utils import timezone

from accounts.models import User
from customers.models import Customer
from products.models import Product
from sales.models import Sale

from .models import SalonAppointment, SalonClientPackage


class SalonAppointmentForm(forms.ModelForm):
    services = forms.ModelMultipleChoiceField(
        queryset=Product.objects.none(),
        widget=forms.SelectMultiple(attrs={"class": "salon-field", "size": 5}),
    )

    class Meta:
        model = SalonAppointment
        fields = [
            "customer", "client_name", "client_phone", "services",
            "stylist", "starts_at", "source", "notes",
        ]
        widgets = {
            "customer": forms.Select(attrs={"class": "salon-field"}),
            "client_name": forms.TextInput(attrs={"class": "salon-field", "autocomplete": "name"}),
            "client_phone": forms.TextInput(attrs={"class": "salon-field", "autocomplete": "tel"}),
            "stylist": forms.Select(attrs={"class": "salon-field"}),
            "starts_at": forms.DateTimeInput(
                attrs={"class": "salon-field", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "source": forms.Select(attrs={"class": "salon-field"}),
            "notes": forms.Textarea(attrs={"class": "salon-field", "rows": 2}),
        }

    def __init__(self, *args, business, **kwargs):
        self.business = business
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.filter(
            business=business, is_active=True
        ).order_by("name")
        self.fields["customer"].required = False
        self.fields["services"].queryset = Product.objects.filter(
            business=business,
            is_active=True,
            metadata__salon_service=True,
        ).order_by("name")
        self.fields["stylist"].queryset = User.objects.filter(
            business=business,
            role__in=["STAFF", "MANAGER"],
            is_active=True,
        ).order_by("first_name", "last_name")
        self.fields["stylist"].required = False
        self.fields["client_name"].required = False
        self.fields["client_phone"].required = False
        if not self.instance.pk and not self.initial.get("starts_at"):
            self.initial["starts_at"] = timezone.localtime() + timedelta(hours=1)

    def clean(self):
        cleaned_data = super().clean()
        customer = cleaned_data.get("customer")
        client_name = cleaned_data.get("client_name", "").strip()
        services = cleaned_data.get("services")
        starts_at = cleaned_data.get("starts_at")
        if not customer and not client_name:
            self.add_error("client_name", "Choose a client or enter the client's name.")
        if customer and not cleaned_data.get("client_phone"):
            cleaned_data["client_phone"] = customer.phone
        if services is not None and not services.exists():
            self.add_error("services", "Choose at least one active salon service.")
        if starts_at and starts_at < timezone.now():
            self.add_error("starts_at", "Choose a time that is not in the past.")
        return cleaned_data


class SalonServiceForm(forms.Form):
    name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={"class": "salon-field", "placeholder": "e.g. Hair colour"}),
    )
    price = forms.DecimalField(
        min_value=0,
        decimal_places=2,
        max_digits=12,
        widget=forms.NumberInput(attrs={"class": "salon-field", "min": "0", "step": "0.01"}),
    )
    duration_min = forms.IntegerField(
        min_value=1,
        max_value=600,
        initial=30,
        widget=forms.NumberInput(attrs={"class": "salon-field", "min": "1", "max": "600"}),
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "salon-field", "rows": 2}),
    )

    def __init__(self, *args, business, **kwargs):
        self.business = business
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if Product.objects.filter(
            business=self.business,
            name__iexact=name,
            metadata__salon_service=True,
        ).exists():
            raise forms.ValidationError("A salon service with this name already exists.")
        return name


class SalonClientPackageForm(forms.ModelForm):
    class Meta:
        model = SalonClientPackage
        fields = [
            "customer",
            "name",
            "services",
            "sessions_total",
            "purchased_at",
            "expires_at",
            "purchase_sale",
            "notes",
        ]
        widgets = {
            "customer": forms.Select(attrs={"class": "salon-field"}),
            "name": forms.TextInput(attrs={"class": "salon-field", "placeholder": "e.g. Wash & style bundle"}),
            "services": forms.SelectMultiple(attrs={"class": "salon-field", "size": 5}),
            "sessions_total": forms.NumberInput(attrs={"class": "salon-field", "min": 1}),
            "purchased_at": forms.DateInput(attrs={"class": "salon-field", "type": "date"}),
            "expires_at": forms.DateInput(attrs={"class": "salon-field", "type": "date"}),
            "purchase_sale": forms.Select(attrs={"class": "salon-field"}),
            "notes": forms.Textarea(attrs={"class": "salon-field", "rows": 2}),
        }

    def __init__(self, *args, business, **kwargs):
        self.business = business
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.filter(
            business=business,
            is_active=True,
        ).order_by("name")
        self.fields["services"].queryset = Product.objects.filter(
            business=business,
            is_active=True,
            metadata__salon_service=True,
        ).order_by("name")
        self.fields["services"].required = True
        self.fields["purchase_sale"].queryset = Sale.objects.filter(
            business=business,
            customer__isnull=False,
        ).select_related("customer").order_by("-sale_date")
        self.fields["purchase_sale"].required = False
        self.fields["purchase_sale"].label = "Related recorded sale (optional)"

    def clean(self):
        cleaned_data = super().clean()
        customer = cleaned_data.get("customer")
        services = cleaned_data.get("services")
        purchased_at = cleaned_data.get("purchased_at")
        expires_at = cleaned_data.get("expires_at")
        purchase_sale = cleaned_data.get("purchase_sale")
        if services is not None and not services.exists():
            self.add_error("services", "Choose at least one active salon service.")
        if purchased_at and expires_at and expires_at < purchased_at:
            self.add_error("expires_at", "Expiry must be on or after the purchase date.")
        if purchase_sale and customer and purchase_sale.customer_id != customer.id:
            self.add_error("purchase_sale", "Choose a sale recorded for this client.")
        return cleaned_data


class SalonPackageRedemptionForm(forms.Form):
    client_package = forms.ModelChoiceField(
        queryset=SalonClientPackage.objects.none(),
        label="Client package",
        widget=forms.Select(attrs={"class": "salon-field"}),
    )
    service = forms.ModelChoiceField(
        queryset=Product.objects.none(),
        widget=forms.Select(attrs={"class": "salon-field"}),
    )
    appointment = forms.ModelChoiceField(
        queryset=SalonAppointment.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "salon-field"}),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "salon-field", "placeholder": "Optional note"}),
    )

    def __init__(self, *args, business, **kwargs):
        self.business = business
        super().__init__(*args, **kwargs)
        self.fields["client_package"].queryset = (
            SalonClientPackage.objects.filter(
                business=business,
                sessions_redeemed__lt=F("sessions_total"),
            ).filter(Q(expires_at__isnull=True) | Q(expires_at__gte=timezone.localdate()))
            .select_related("customer")
            .order_by("customer__name", "name")
        )
        self.fields["appointment"].queryset = SalonAppointment.objects.filter(
            business=business,
            status__in=["CHECKED_IN", "IN_SERVICE"],
        ).select_related("customer").order_by("starts_at")
        self.fields["appointment"].label = "Current appointment (optional)"
        self.fields["service"].queryset = Product.objects.filter(
            business=business,
            is_active=True,
            metadata__salon_service=True,
        ).order_by("name")

    def clean(self):
        cleaned_data = super().clean()
        package = cleaned_data.get("client_package")
        appointment = cleaned_data.get("appointment")
        service = cleaned_data.get("service")
        if package and not package.is_usable:
            self.add_error("client_package", "This package has no usable sessions or has expired.")
        if package and service and not package.services.filter(id=service.id).exists():
            self.add_error("service", "Choose a service included in this package.")
        if appointment and package and appointment.customer_id != package.customer_id:
            self.add_error("appointment", "The appointment client does not match this package.")
        if appointment and service and not appointment.services.filter(id=service.id).exists():
            self.add_error("appointment", "The service is not included in this appointment.")
        return cleaned_data
