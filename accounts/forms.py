from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm as BasePasswordChangeForm
from django.core.validators import MinLengthValidator
from .models import User

class UserRegistrationForm(forms.ModelForm):
    """Form for user registration."""

    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={
            "class": "input-field",
            "placeholder": "smartbiz@gmail.com",
            "autocomplete": "email",
        }),
        error_messages={"invalid": "Enter a valid email address."},
    )
    
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'class': 'input-field'}),
        validators=[MinLengthValidator(8)]
    )
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={'class': 'input-field'})
    )
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone_number', 'role']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'input-field'}),
            'last_name': forms.TextInput(attrs={'class': 'input-field'}),
            'email': forms.EmailInput(attrs={'class': 'input-field'}),
            'phone_number': forms.TextInput(attrs={'class': 'input-field'}),
            'role': forms.Select(attrs={'class': 'input-field'}),
        }
    
    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('A user with this email already exists.')
        return email
    
    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1:
            password_validation.validate_password(password1, self.instance)
        
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError('Passwords do not match.')
        
        return cleaned_data
    
    def __init__(self, *args, **kwargs):
        self.allow_role = kwargs.pop("allow_role", False)
        allowed_roles = kwargs.pop("allowed_roles", None)
        super().__init__(*args, **kwargs)
        if not self.allow_role:
            self.fields.pop("role")
        elif allowed_roles is not None:
            self.fields["role"].choices = [
                choice for choice in self.fields["role"].choices
                if choice[0] in allowed_roles
            ]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        user.is_active = True
        if not self.allow_role:
            user.role = "OWNER"
        if commit:
            user.save()
        return user

class UserLoginForm(forms.Form):
    """Form for user login."""
    
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'input-field', 'placeholder': 'you@business.com'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'input-field', 'placeholder': '••••••••'})
    )
    remember = forms.BooleanField(required=False)

class UserProfileForm(forms.ModelForm):
    """Form for updating user profile."""
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone_number', 'profile_picture']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'input-field'}),
            'last_name': forms.TextInput(attrs={'class': 'input-field'}),
            'email': forms.EmailInput(attrs={'class': 'input-field'}),
            'phone_number': forms.TextInput(attrs={'class': 'input-field'}),
            'profile_picture': forms.FileInput(attrs={'class': 'input-field'}),
        }

class UserUpdateForm(forms.ModelForm):
    """Form for admin to update users."""
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone_number', 'role', 'is_active']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'input-field'}),
            'last_name': forms.TextInput(attrs={'class': 'input-field'}),
            'email': forms.EmailInput(attrs={'class': 'input-field'}),
            'phone_number': forms.TextInput(attrs={'class': 'input-field'}),
            'role': forms.Select(attrs={'class': 'input-field'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }

    def __init__(self, *args, **kwargs):
        allowed_roles = kwargs.pop("allowed_roles", None)
        super().__init__(*args, **kwargs)
        if allowed_roles is not None:
            self.fields["role"].choices = [
                choice for choice in self.fields["role"].choices
                if choice[0] in allowed_roles
            ]

class PasswordResetForm(forms.Form):
    """Form for password reset request."""
    
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'input-field'})
    )
    
    def clean_email(self):
        email = self.cleaned_data['email']
        if not User.objects.filter(email=email).exists():
            raise forms.ValidationError('No user found with this email address.')
        return email

class PasswordChangeForm(BasePasswordChangeForm):
    """Form for changing password."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'input-field'})