from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
from django.core.validators import MinLengthValidator
import uuid

class UserManager(BaseUserManager):
    """Custom user manager for the User model."""
    
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', 'ADMIN')
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(email, password, **extra_fields)

class User(AbstractUser):
    """Custom User model with roles and business association."""
    
    ROLE_CHOICES = [
        ('SUPER_ADMIN', 'Super Admin'),
        ('ADMIN', 'Platform Admin'),
        ('OWNER', 'Business Owner'),
        ('MANAGER', 'Business Manager'),
        ('STAFF', 'Staff Member'),
        ('ACCOUNTANT', 'Accountant / Bookkeeper'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    username = None  # Remove username field
    
    # Personal information
    phone_number = models.CharField(max_length=15, blank=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', null=True, blank=True)
    
    # Role and permissions
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='STAFF')
    business = models.ForeignKey(
        'businesses.Business',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users'
    )
    
    # Status fields
    is_active = models.BooleanField(default=True)
    is_email_verified = models.BooleanField(default=False)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity = models.DateTimeField(auto_now=True)
    
    # Preferences
    preferences = models.JSONField(default=dict, blank=True)
    
    objects = UserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']
    
    class Meta:
        db_table = 'accounts_user'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['business']),
            models.Index(fields=['role']),
        ]
    
    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"
    
    @property
    def full_name(self):
        return self.get_full_name()
    
    @property
    def is_business_owner(self):
        return self.role == 'OWNER'
    
    @property
    def is_business_manager(self):
        return self.role in ['OWNER', 'MANAGER']
    
    @property
    def can_manage_business(self):
        return self.role in ['OWNER', 'MANAGER', 'ADMIN']
    
    def has_permission(self, permission):
        """Return whether this user may perform a named business action."""
        if self.is_superuser or self.role in {'ADMIN', 'OWNER'}:
            return True
        permissions = {
            'MANAGER': {
                'view_dashboard', 'view_analytics', 'record_sales',
                'manage_inventory', 'submit_expenses', 'approve_expenses',
                'manage_products', 'view_ai_insights', 'chat_assistant',
            },
            'STAFF': {
                'view_dashboard', 'record_sales', 'update_stock_counts',
                'submit_expenses', 'chat_assistant_limited',
            },
            'ACCOUNTANT': {
                'view_dashboard_financial', 'review_expenses',
                'view_ai_insights_financial', 'chat_assistant_limited',
                'export_reports',
            },
        }
        return permission in permissions.get(self.role, set())
    
    def get_businesses(self):
        """Get all businesses the user has access to."""
        if self.is_superuser or self.role == 'ADMIN':
            from businesses.models import Business
            return Business.objects.all()
        if self.business:
            return [self.business]
        return []
    
    def get_user_permissions_list(self):
        """Return capability flags for templates and API consumers."""
        capabilities = {
            'view_dashboard': 'view_dashboard',
            'record_sales': 'record_sales',
            'manage_products': 'manage_products',
            'manage_inventory': 'manage_inventory',
            'update_stock_counts': 'update_stock_counts',
            'submit_expenses': 'submit_expenses',
            'approve_expenses': 'approve_expenses',
            'review_expenses': 'review_expenses',
            'view_ai_insights': 'view_ai_insights',
            'export_reports': 'export_reports',
            'manage_users': 'manage_roles',
            'manage_business': 'manage_business_settings',
        }
        return {
            name: self.has_permission(permission)
            for name, permission in capabilities.items()
        }

class UserActivity(models.Model):
    """Track user activity for audit purposes."""
    
    ACTION_CHOICES = [
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('VIEW', 'View'),
        ('EXPORT', 'Export'),
        ('IMPORT', 'Import'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    business = models.ForeignKey('businesses.Business', on_delete=models.CASCADE, null=True, blank=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'accounts_user_activity'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['business', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.action} - {self.timestamp}"

class UserSession(models.Model):
    """Track user sessions."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    session_key = models.CharField(max_length=40, unique=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    last_activity = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'accounts_user_session'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.created_at}"