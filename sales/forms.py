from django import forms
from django.core.validators import MinValueValidator
from django.forms import inlineformset_factory
from .models import Sale, SaleItem, Payment, Return
from products.models import Product

class SaleForm(forms.ModelForm):
    """Form for creating/editing sales."""
    
    class Meta:
        model = Sale
        fields = [
            'customer', 'customer_name', 'customer_phone', 'customer_email',
            'payment_method', 'notes', 'delivery_address', 'delivery_date',
        ]
        widgets = {
            'customer': forms.Select(attrs={'class': 'input-field'}),
            'customer_name': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Walk-in Customer'}),
            'customer_phone': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Phone number'}),
            'customer_email': forms.EmailInput(attrs={'class': 'input-field', 'placeholder': 'Email address'}),
            'payment_method': forms.Select(attrs={'class': 'input-field'}),
            'notes': forms.Textarea(attrs={'class': 'input-field', 'rows': 2, 'placeholder': 'Additional notes'}),
            'delivery_address': forms.Textarea(attrs={'class': 'input-field', 'rows': 2, 'placeholder': 'Delivery address'}),
            'delivery_date': forms.DateTimeInput(attrs={'class': 'input-field', 'type': 'datetime-local'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.business = kwargs.pop('business', None)
        super().__init__(*args, **kwargs)
        
        if self.business:
            from customers.models import Customer
            self.fields['customer'].queryset = Customer.objects.filter(
                business=self.business,
                is_active=True
            )

class SaleItemForm(forms.ModelForm):
    """Form for sale items."""
    
    class Meta:
        model = SaleItem
        fields = ['product', 'quantity', 'unit_price']
        widgets = {
            'product': forms.Select(attrs={'class': 'input-field product-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'input-field', 'min': 1, 'value': 1}),
            'unit_price': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01', 'min': 0}),
        }
    
    def __init__(self, *args, **kwargs):
        self.business = kwargs.pop('business', None)
        super().__init__(*args, **kwargs)
        
        if self.business:
            self.fields['product'].queryset = Product.objects.filter(
                business=self.business,
                is_active=True
            )

class BaseSaleItemFormSet(forms.BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        self.business = kwargs.pop("business", None)
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["business"] = self.business
        return kwargs


SaleItemFormSet = inlineformset_factory(
    Sale,
    SaleItem,
    form=SaleItemForm,
    formset=BaseSaleItemFormSet,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)

class PaymentForm(forms.ModelForm):
    """Form for processing payments."""
    
    class Meta:
        model = Payment
        fields = ['amount', 'payment_method', 'mpesa_phone', 'reference_number', 'notes']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01', 'min': 0}),
            'payment_method': forms.Select(attrs={'class': 'input-field'}),
            'mpesa_phone': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'M-PESA phone number'}),
            'reference_number': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Reference number'}),
            'notes': forms.Textarea(attrs={'class': 'input-field', 'rows': 2}),
        }
    
    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount <= 0:
            raise forms.ValidationError('Amount must be greater than zero.')
        return amount

class ReturnForm(forms.ModelForm):
    """Form for processing returns."""
    
    class Meta:
        model = Return
        fields = ['items', 'refund_amount', 'restocking_fee', 'reason', 'notes']
        widgets = {
            'items': forms.Textarea(attrs={'class': 'input-field', 'rows': 3, 'placeholder': 'JSON format: {"product_id": quantity}'}),
            'refund_amount': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01', 'min': 0}),
            'restocking_fee': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01', 'min': 0}),
            'reason': forms.Textarea(attrs={'class': 'input-field', 'rows': 2}),
            'notes': forms.Textarea(attrs={'class': 'input-field', 'rows': 2}),
        }

class SaleSearchForm(forms.Form):
    """Form for searching/filtering sales."""
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input-field',
            'placeholder': 'Search by invoice number, customer...',
        })
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'input-field', 'type': 'date'})
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'input-field', 'type': 'date'})
    )
    payment_status = forms.ChoiceField(
        choices=[('', 'All Status')] + Sale.PAYMENT_STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'input-field'})
    )
    payment_method = forms.ChoiceField(
        choices=[('', 'All Methods')] + Sale.PAYMENT_METHOD_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'input-field'})
    )
    min_amount = forms.DecimalField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'input-field', 'placeholder': 'Min'})
    )
    max_amount = forms.DecimalField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'input-field', 'placeholder': 'Max'})
    )