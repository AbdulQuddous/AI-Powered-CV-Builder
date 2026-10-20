"""Use email-based account administration for the project's custom user model."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm

from .models import User


class AccountCreationForm(AdminUserCreationForm):
    class Meta(AdminUserCreationForm.Meta):
        model = User
        fields = ('email', 'full_name')


class AccountChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = '__all__'


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    add_form = AccountCreationForm
    form = AccountChangeForm
    list_display = ('email', 'full_name', 'is_staff', 'is_active')
    search_fields = ('email', 'full_name')
    ordering = ('email',)
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal details', {'fields': ('full_name',)}),
        ('Permissions', {'fields': (
            'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions',
        )}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': (
            'email', 'full_name', 'usable_password', 'password1', 'password2',
        )}),
    )
