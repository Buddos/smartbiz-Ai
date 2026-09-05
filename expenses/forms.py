from django import forms

from .models import Expense, ExpenseCategory


class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ["name", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input-field"}),
            "description": forms.Textarea(attrs={"class": "input-field", "rows": 2}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
        }


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ["category", "title", "amount", "expense_date", "payment_method", "vendor", "notes", "receipt"]
        widgets = {
            "category": forms.Select(attrs={"class": "input-field"}),
            "title": forms.TextInput(attrs={"class": "input-field"}),
            "amount": forms.NumberInput(attrs={"class": "input-field", "step": "0.01", "min": 0}),
            "expense_date": forms.DateInput(attrs={"class": "input-field", "type": "date"}),
            "payment_method": forms.Select(attrs={"class": "input-field"}),
            "vendor": forms.TextInput(attrs={"class": "input-field"}),
            "notes": forms.Textarea(attrs={"class": "input-field", "rows": 2}),
            "receipt": forms.FileInput(attrs={"class": "input-field"}),
        }

    def __init__(self, *args, **kwargs):
        business = kwargs.pop("business", None)
        super().__init__(*args, **kwargs)
        if business:
            self.fields["category"].queryset = ExpenseCategory.objects.filter(
                business=business, is_active=True
            )
