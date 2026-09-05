from django import forms
from django.core.validators import MinValueValidator
from .models import InventoryTransaction, StockCount, StockCountItem, InventoryAlert
from products.models import Product

class InventoryTransactionForm(forms.ModelForm):
    """Form for creating inventory transactions."""
    
    class Meta:
        model = InventoryTransaction
        fields = [
            'product', 'transaction_type', 'quantity', 'unit_cost',
            'reference_number', 'notes'
        ]
        widgets = {
            'product': forms.Select(attrs={'class': 'input-field'}),
            'transaction_type': forms.Select(attrs={'class': 'input-field'}),
            'quantity': forms.NumberInput(attrs={'class': 'input-field', 'min': 1}),
            'unit_cost': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01', 'min': 0}),
            'reference_number': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'PO #, Invoice #'}),
            'notes': forms.Textarea(attrs={'class': 'input-field', 'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        self.business = kwargs.pop('business', None)
        super().__init__(*args, **kwargs)
        
        if self.business:
            self.fields['product'].queryset = Product.objects.filter(
                business=self.business,
                is_active=True
            )
    
    def clean_quantity(self):
        quantity = self.cleaned_data.get('quantity')
        transaction_type = self.cleaned_data.get('transaction_type')
        product = self.cleaned_data.get('product')
        
        if transaction_type in ['SALE', 'WASTE', 'RETURNED_TO_SUPPLIER']:
            if product and quantity > product.current_stock:
                raise forms.ValidationError(
                    f'Not enough stock. Available: {product.current_stock}'
                )
        return quantity

class StockCountForm(forms.ModelForm):
    """Form for creating stock counts."""
    
    class Meta:
        model = StockCount
        fields = ['count_date', 'location', 'notes']
        widgets = {
            'count_date': forms.DateInput(attrs={'class': 'input-field', 'type': 'date'}),
            'location': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Warehouse, Store, etc.'}),
            'notes': forms.Textarea(attrs={'class': 'input-field', 'rows': 2}),
        }

class StockCountItemForm(forms.ModelForm):
    """Form for stock count items."""
    
    class Meta:
        model = StockCountItem
        fields = ['product', 'expected_quantity', 'counted_quantity', 'notes']
        widgets = {
            'product': forms.Select(attrs={'class': 'input-field'}),
            'expected_quantity': forms.NumberInput(attrs={'class': 'input-field', 'min': 0}),
            'counted_quantity': forms.NumberInput(attrs={'class': 'input-field', 'min': 0}),
            'notes': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Notes'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.business = kwargs.pop('business', None)
        super().__init__(*args, **kwargs)
        
        if self.business:
            self.fields['product'].queryset = Product.objects.filter(
                business=self.business,
                is_active=True
            )

class StockAdjustmentForm(forms.Form):
    """Form for bulk stock adjustments."""
    
    product = forms.ModelChoiceField(
        queryset=Product.objects.none(),
        widget=forms.Select(attrs={'class': 'input-field'})
    )
    adjustment_type = forms.ChoiceField(
        choices=[
            ('add', 'Add Stock'),
            ('subtract', 'Subtract Stock'),
            ('set', 'Set Stock'),
        ],
        widget=forms.Select(attrs={'class': 'input-field'})
    )
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'input-field', 'min': 1})
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'input-field', 'rows': 2, 'placeholder': 'Reason for adjustment'})
    )
    
    def __init__(self, *args, **kwargs):
        business = kwargs.pop('business', None)
        super().__init__(*args, **kwargs)
        
        if business:
            self.fields['product'].queryset = Product.objects.filter(
                business=business,
                is_active=True
            )

class InventorySearchForm(forms.Form):
    """Form for searching inventory transactions."""
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'input-field',
            'placeholder': 'Search by product, reference...'
        })
    )
    transaction_type = forms.ChoiceField(
        choices=[('', 'All Types')] + InventoryTransaction.TRANSACTION_TYPES,
        required=False,
        widget=forms.Select(attrs={'class': 'input-field'})
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'input-field', 'type': 'date'})
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'input-field', 'type': 'date'})
    )
    status = forms.ChoiceField(
        choices=[('', 'All Status')] + InventoryTransaction.TRANSACTION_STATUS,
        required=False,
        widget=forms.Select(attrs={'class': 'input-field'})
    )