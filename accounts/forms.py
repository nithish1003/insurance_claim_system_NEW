from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from .models import User, UserProfile


class RegisterForm(forms.ModelForm):

    full_name = forms.CharField(
        max_length=255, 
        required=True, 
        label="Full Name",
        widget=forms.TextInput(attrs={'placeholder': 'Enter your full name as per Aadhaar'})
    )
    
    aadhaar_number = forms.CharField(
        max_length=12, 
        min_length=12, 
        required=True, 
        label="Aadhaar Number",
        validators=[RegexValidator(r'^\d{12}$', 'Aadhaar must be exactly 12 numeric digits.')],
        widget=forms.TextInput(attrs={'placeholder': '12-digit Aadhaar Number'})
    )
    
    id_proof = forms.FileField(
        required=True, 
        label="Upload ID Proof",
        help_text="Upload a clear image or PDF of your ID proof"
    )

    password = forms.CharField(
        widget=forms.PasswordInput,
        min_length=8,
        error_messages={
            "required": "Password is required.",
            "min_length": "Password must be at least 8 characters long.",
        },
    )

    confirm_password = forms.CharField(
        widget=forms.PasswordInput,
        error_messages={
            "required": "Please confirm your password.",
        },
    )

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "phone",
            "address",
            "role",
            "password",
        ]


    def clean_email(self):
        email = self.cleaned_data.get("email")
        if not email:
            return email
        if User.objects.filter(email=email).exists():
            raise ValidationError("Email already exists")
        return email

    def clean_aadhaar_number(self):
        aadhaar = self.cleaned_data.get("aadhaar_number")
        if UserProfile.objects.filter(aadhaar_number=aadhaar).exists():
            raise ValidationError("A user with this Aadhaar number is already registered.")
        return aadhaar

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        confirm = cleaned.get("confirm_password")

        if password and confirm and password != confirm:
            raise ValidationError("Passwords do not match")
        return cleaned


class ProfileEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone", "address"]


from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm

class CustomPasswordResetForm(PasswordResetForm):
    def clean_email(self):
        email = self.cleaned_data.get('email')
        # We don't raise validation error if email doesn't exist
        # to prevent user enumeration. This is handled by Django's
        # default PasswordResetForm but we can be explicit here.
        return email

class CustomSetPasswordForm(SetPasswordForm):
    # This form is used for the actual reset.
    # It inherits password validation from SetPasswordForm.
    pass