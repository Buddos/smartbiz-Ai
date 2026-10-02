from django import forms
from customers.models import Customer
from products.models import Product
from sales.models import Sale

from .models import CreditPlan, RepairJob, Supplier

INPUT_CLASS = "input-field"


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ["name", "phone", "email", "lead_time_days", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "phone": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "email": forms.EmailInput(attrs={"class": INPUT_CLASS}),
            "lead_time_days": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 0}),
            "notes": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 2}),
        }


class PurchaseOrderForm(forms.Form):
    supplier = forms.ModelChoiceField(queryset=Supplier.objects.none(), widget=forms.Select(attrs={"class": INPUT_CLASS}))
    product = forms.ModelChoiceField(queryset=Product.objects.none(), widget=forms.Select(attrs={"class": INPUT_CLASS}))
    quantity = forms.IntegerField(min_value=1, widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 1}))
    unit_cost = forms.DecimalField(min_value=0, decimal_places=2, max_digits=12, widget=forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 0, "step": "0.01"}))
    expected_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 2}))

    def __init__(self, *args, business, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supplier"].queryset = Supplier.objects.filter(business=business, is_active=True)
        self.fields["product"].queryset = Product.objects.filter(business=business, is_active=True).order_by("name")


class RepairJobForm(forms.ModelForm):
    class Meta:
        model = RepairJob
        fields = [
            "customer", "customer_name", "customer_phone", "device_brand", "device_model",
            "imei", "issue", "estimate", "deposit", "promised_date", "technician", "notes",
        ]
        widgets = {
            "customer": forms.Select(attrs={"class": INPUT_CLASS}),
            "customer_name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "customer_phone": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "device_brand": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "device_model": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "imei": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "issue": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 3}),
            "estimate": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 0, "step": "0.01"}),
            "deposit": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 0, "step": "0.01"}),
            "promised_date": forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}),
            "technician": forms.Select(attrs={"class": INPUT_CLASS}),
            "notes": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 2}),
        }

    def __init__(self, *args, business, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.filter(business=business, is_active=True)
        self.fields["customer"].required = False
        self.fields["customer_name"].required = False
        self.fields["technician"].queryset = business.users.filter(is_active=True).order_by("first_name", "last_name")
        self.fields["technician"].required = False

    def clean(self):
        cleaned = super().clean()
        customer = cleaned.get("customer")
        if customer:
            cleaned["customer_name"] = customer.name
            if not cleaned.get("customer_phone"):
                cleaned["customer_phone"] = customer.phone
        elif not cleaned.get("customer_name"):
            self.add_error("customer_name", "Enter a customer name or select an existing customer.")
        return cleaned


class CreditPlanForm(forms.ModelForm):
    class Meta:
        model = CreditPlan
        fields = ["sale", "installment_count", "next_due_date", "notes"]
        widgets = {
            "sale": forms.Select(attrs={"class": INPUT_CLASS}),
            "installment_count": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 1}),
            "next_due_date": forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}),
            "notes": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 2}),
        }

    def __init__(self, *args, business, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sale"].queryset = (
            Sale.objects.filter(business=business, balance_due__gt=0)
            .filter(payment_method="CREDIT")
            .filter(credit_plan__isnull=True)
            .select_related("customer")
            .order_by("-sale_date")
        )
