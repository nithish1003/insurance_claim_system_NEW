from django.contrib import admin

from .models import User, PasswordResetAttempt, UserProfile

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Identity Verification'
    readonly_fields = ('aadhaar_number', 'full_name', 'id_proof')

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'role', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    inlines = [UserProfileInline]

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'full_name', 'masked_aadhaar', 'is_verified', 'created_at')
    list_filter = ('is_verified', 'created_at')
    search_fields = ('user__username', 'full_name', 'aadhaar_number')
    readonly_fields = ('aadhaar_number',)

@admin.register(PasswordResetAttempt)
class PasswordResetAttemptAdmin(admin.ModelAdmin):
    list_display = ('email', 'user', 'ip_address', 'status', 'token_used', 'created_at')
    list_filter = ('status', 'token_used', 'created_at')
    search_fields = ('email', 'user__username', 'ip_address')
    readonly_fields = ('email', 'user', 'ip_address', 'user_agent', 'status', 'token_used', 'created_at')

    def has_add_permission(self, request):
        return False  # Read-only audit log
