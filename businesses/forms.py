from django import forms
from django.core.validators import MinLengthValidator
from .models import Business, BusinessSettings, BusinessBranch

class BusinessSetupForm(forms.ModelForm):
    """Form for initial business setup."""
    
    class Meta:
        model = Business
        fields = [
            'name', 'business_type', 'business_size',
            'email', 'phone_number', 'address', 'city', 'county',
            'description', 'registration_number', 'tax_id',
            'currency', 'timezone'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'e.g., Amina\'s Grocery Store'}),
            'business_type': forms.Select(attrs={'class': 'input-field'}),
            'business_size': forms.Select(attrs={'class': 'input-field'}),
            'email': forms.EmailInput(attrs={'class': 'input-field', 'placeholder': 'business@email.com'}),
            'phone_number': forms.TextInput(attrs={'class': 'input-field', 'placeholder': '+254 700 000 000'}),
            'address': forms.Textarea(attrs={'class': 'input-field', 'rows': 2, 'placeholder': 'Street address'}),
            'city': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Nairobi'}),
            'county': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Nairobi County'}),
            'description': forms.Textarea(attrs={'class': 'input-field', 'rows': 3, 'placeholder': 'Brief description of your business'}),
            'registration_number': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Business registration number'}),
            'tax_id': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'KRA PIN (optional)'}),
            'currency': forms.Select(attrs={'class': 'input-field'}),
            'timezone': forms.Select(attrs={'class': 'input-field'}),
        }
    
    def clean_name(self):
        name = self.cleaned_data.get('name')
        if len(name) < 2:
            raise forms.ValidationError('Business name must be at least 2 characters.')
        return name
    
    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number')
        if not phone:
            raise forms.ValidationError('Phone number is required.')
        return phone

class BusinessUpdateForm(forms.ModelForm):
    """Form for updating business details."""
    
    class Meta:
        model = Business
        fields = [
            'name', 'business_type', 'business_size',
            'email', 'phone_number', 'address', 'city', 'county',
            'description', 'registration_number', 'tax_id',
            'logo', 'currency', 'timezone'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'input-field'}),
            'business_type': forms.Select(attrs={'class': 'input-field'}),
            'business_size': forms.Select(attrs={'class': 'input-field'}),
            'email': forms.EmailInput(attrs={'class': 'input-field'}),
            'phone_number': forms.TextInput(attrs={'class': 'input-field'}),
            'address': forms.Textarea(attrs={'class': 'input-field', 'rows': 2}),
            'city': forms.TextInput(attrs={'class': 'input-field'}),
            'county': forms.TextInput(attrs={'class': 'input-field'}),
            'description': forms.Textarea(attrs={'class': 'input-field', 'rows': 3}),
            'registration_number': forms.TextInput(attrs={'class': 'input-field'}),
            'tax_id': forms.TextInput(attrs={'class': 'input-field'}),
            'logo': forms.FileInput(attrs={'class': 'input-field'}),
            'currency': forms.Select(attrs={'class': 'input-field'}),
            'timezone': forms.Select(attrs={'class': 'input-field'}),
        }

class BusinessSettingsForm(forms.ModelForm):
    """Form for business settings."""
    
    class Meta:
        model = BusinessSettings
        exclude = ['business']
        widgets = {
            'invoice_prefix': forms.TextInput(attrs={'class': 'input-field'}),
            'invoice_footer': forms.Textarea(attrs={'class': 'input-field', 'rows': 2}),
            'invoice_tax_rate': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01'}),
            'invoice_terms': forms.Textarea(attrs={'class': 'input-field', 'rows': 2}),
            'receipt_footer': forms.Textarea(attrs={'class': 'input-field', 'rows': 2}),
            'show_stock_on_receipt': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'email_notifications': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'sms_notifications': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'alert_low_stock': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'alert_daily_summary': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'alert_weekly_summary': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'tax_enabled': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'tax_rate': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01'}),
            'tax_inclusive': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'email_sender': forms.EmailInput(attrs={'class': 'input-field'}),
            'email_subject_prefix': forms.TextInput(attrs={'class': 'input-field'}),
            'auto_backup': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'backup_frequency': forms.Select(attrs={'class': 'input-field'}),
        }

class BusinessBranchForm(forms.ModelForm):
    """Form for business branches."""
    
    class Meta:
        model = BusinessBranch
        fields = [
            'name', 'address', 'city', 'county',
            'phone_number', 'email', 'is_main',
            'latitude', 'longitude', 'operating_hours'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'input-field'}),
            'address': forms.Textarea(attrs={'class': 'input-field', 'rows': 2}),
            'city': forms.TextInput(attrs={'class': 'input-field'}),
            'county': forms.TextInput(attrs={'class': 'input-field'}),
            'phone_number': forms.TextInput(attrs={'class': 'input-field'}),
            'email': forms.EmailInput(attrs={'class': 'input-field'}),
            'is_main': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'latitude': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.0000001'}),
            'longitude': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.0000001'}),
            'operating_hours': forms.Textarea(attrs={'class': 'input-field', 'rows': 3, 'placeholder': 'JSON format for operating hours'}),
        }