from django import forms

from .models import Category, Product


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "description", "icon", "color", "parent", "is_active", "display_order"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input-field"}),
            "description": forms.Textarea(attrs={"class": "input-field", "rows": 2}),
            "icon": forms.TextInput(attrs={"class": "input-field", "placeholder": "fa-box"}),
            "color": forms.TextInput(attrs={"class": "input-field", "placeholder": "#0F6E56"}),
            "parent": forms.Select(attrs={"class": "input-field"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
            "display_order": forms.NumberInput(attrs={"class": "input-field"}),
        }

    def __init__(self, *args, **kwargs):
        business = kwargs.pop("business", None)
        super().__init__(*args, **kwargs)
        if business:
            qs = Category.objects.filter(business=business)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            self.fields["parent"].queryset = qs
            self.fields["parent"].required = False


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name", "sku", "barcode", "category", "purchase_price", "selling_price",
            "wholesale_price", "discount_price", "unit", "current_stock", "minimum_stock",
            "maximum_stock", "reorder_level", "reorder_quantity", "supplier_name",
            "supplier_contact", "supplier_notes", "description", "image", "is_active",
            "is_taxable",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input-field"}),
            "sku": forms.TextInput(attrs={"class": "input-field"}),
            "barcode": forms.TextInput(attrs={"class": "input-field"}),
            "category": forms.Select(attrs={"class": "input-field"}),
            "purchase_price": forms.NumberInput(attrs={"class": "input-field", "step": "0.01"}),
            "selling_price": forms.NumberInput(attrs={"class": "input-field", "step": "0.01"}),
            "wholesale_price": forms.NumberInput(attrs={"class": "input-field", "step": "0.01"}),
            "discount_price": forms.NumberInput(attrs={"class": "input-field", "step": "0.01"}),
            "unit": forms.Select(attrs={"class": "input-field"}),
            "current_stock": forms.NumberInput(attrs={"class": "input-field", "min": 0}),
            "minimum_stock": forms.NumberInput(attrs={"class": "input-field", "min": 0}),
            "maximum_stock": forms.NumberInput(attrs={"class": "input-field", "min": 0}),
            "reorder_level": forms.NumberInput(attrs={"class": "input-field", "min": 0}),
            "reorder_quantity": forms.NumberInput(attrs={"class": "input-field", "min": 1}),
            "supplier_name": forms.TextInput(attrs={"class": "input-field"}),
            "supplier_contact": forms.TextInput(attrs={"class": "input-field"}),
            "supplier_notes": forms.Textarea(attrs={"class": "input-field", "rows": 2}),
            "description": forms.Textarea(attrs={"class": "input-field", "rows": 3}),
            "image": forms.FileInput(attrs={"class": "input-field"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
            "is_taxable": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
        }

    def __init__(self, *args, **kwargs):
        business = kwargs.pop("business", None)
        super().__init__(*args, **kwargs)
        self.fields["sku"].required = False
        if business:
            self.fields["category"].queryset = Category.objects.filter(business=business, is_active=True)
            self.fields["category"].required = False


class ProductSearchForm(forms.Form):
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "input-field", "placeholder": "Name, SKU, barcode..."}),
    )
    category = forms.ModelChoiceField(
        queryset=Category.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "input-field"}),
    )
    status = forms.ChoiceField(
        choices=[("", "All status")] + list(Product.STATUS_CHOICES),
        required=False,
        widget=forms.Select(attrs={"class": "input-field"}),
    )
    low_stock = forms.BooleanField(required=False)
    sort_by = forms.ChoiceField(
        required=False,
        choices=[
            ("", "Name"),
            ("-created_at", "Newest"),
            ("current_stock", "Stock (low first)"),
            ("-current_stock", "Stock (high first)"),
            ("selling_price", "Price"),
        ],
        widget=forms.Select(attrs={"class": "input-field"}),
    )

    def __init__(self, *args, **kwargs):
        business = kwargs.pop("business", None)
        super().__init__(*args, **kwargs)
        if business:
            self.fields["category"].queryset = Category.objects.filter(business=business)


class ProductBulkUploadForm(forms.Form):
    csv_file = forms.FileField(widget=forms.FileInput(attrs={"class": "input-field", "accept": ".csv"}))
