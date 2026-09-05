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
        """Check if user has a specific permission."""
        # Super admin has all permissions
        if self.is_superuser:
            return True
        
        # Platform admin has all permissions
        if self.role == 'ADMIN':
            return True
        
        # Business owner has all business permissions
        if self.role == 'OWNER':
            return True
        
        # Manager has most permissions
        if self.role == 'MANAGER':
            # Managers can't delete business or manage other users' roles
            restricted = ['delete_business', 'manage_roles']
            return permission not in restricted
        
        # Staff have limited permissions
        if self.role == 'STAFF':
            staff_permissions = [
                'view_products', 'create_sales', 'view_sales',
                'view_inventory', 'view_customers'
            ]
            return permission in staff_permissions
        
        return False
    
    def get_businesses(self):
        """Get all businesses the user has access to."""
        if self.is_superuser or self.role == 'ADMIN':
            from businesses.models import Business
            return Business.objects.all()
        if self.business:
            return [self.business]
        return []
    
    def get_user_permissions_list(self):
        """Get list of permissions for the user."""
        permissions = {
            'view_dashboard': True,
            'manage_products': self.can_manage_business,
            'view_products': True,
            'manage_sales': self.can_manage_business or self.role == 'MANAGER',
            'view_sales': True,
            'manage_expenses': self.can_manage_business,
            'view_expenses': True,
            'manage_inventory': self.can_manage_business or self.role == 'MANAGER',
            'view_inventory': True,
            'manage_customers': self.can_manage_business or self.role == 'MANAGER',
            'view_customers': True,
            'manage_users': self.can_manage_business,
            'view_analytics': self.can_manage_business or self.role == 'MANAGER',
            'view_reports': self.can_manage_business or self.role == 'MANAGER',
            'manage_business': self.can_manage_business,
            'delete_business': self.role in ['OWNER', 'ADMIN'],
        }
        return permissions

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