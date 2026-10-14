from django import forms

from .models import Customer, CustomerFeedback


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ["name", "phone", "email", "customer_tier", "address", "notes", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input-field"}),
            "phone": forms.TextInput(attrs={"class": "input-field"}),
            "email": forms.EmailInput(attrs={"class": "input-field"}),
            "customer_tier": forms.TextInput(attrs={
                "class": "input-field", "placeholder": "e.g. Gold or Tier A",
            }),
            "address": forms.Textarea(attrs={"class": "input-field", "rows": 2}),
            "notes": forms.Textarea(attrs={"class": "input-field", "rows": 2}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
        }


class CustomerFeedbackForm(forms.ModelForm):
    class Meta:
        model = CustomerFeedback
        fields = ["rating", "comment"]
        widgets = {
            "rating": forms.NumberInput(attrs={"class": "input-field", "min": 1, "max": 5}),
            "comment": forms.Textarea(attrs={"class": "input-field", "rows": 3}),
        }
