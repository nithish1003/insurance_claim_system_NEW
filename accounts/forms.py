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
        max_length=20, 
        min_length=12, 
        required=True, 
        label="Aadhaar Number",
        widget=forms.TextInput(attrs={'placeholder': 'XXXX XXXX XXXX'})
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
            "full_name",
            "email",
            "phone",
            "aadhaar_number",
            "id_proof",
            "address",
            "password",
            "confirm_password"
        ]


    def __init__(self, *args, **kwargs):
        self.ocr_value = kwargs.pop('ocr_value', None)
        self.ocr_name = kwargs.pop('ocr_name', None)
        super().__init__(*args, **kwargs)

    def clean(self):
        # Initial cleanup and extraction
        self.cleaned_data = super().clean()
        m_aadhaar_raw = self.cleaned_data.get("aadhaar_number")
        m_full_name = self.cleaned_data.get("full_name")
        import re
        from difflib import SequenceMatcher

        # --- STEP 1: IDENTITY GOVERNANCE (CRITICAL GATING) ---
        # We enforce a strictly prioritized validation order based on identity proofing.
        
        # 1.1 Aadhaar Format & Normalization
        m_clean = ""
        if m_aadhaar_raw:
            m_clean = re.sub(r'\D', '', str(m_aadhaar_raw))
            if len(m_clean) != 12:
                self._errors = {}
                raise ValidationError("Invalid Aadhaar number: Must be exactly 12 numeric digits.")

        # 1.2 Aadhaar OCR Cross-Match
        if m_aadhaar_raw and self.ocr_value:
            o_clean = re.sub(r'\D', '', str(self.ocr_value))
            
            # 🔥 PRODUCTION AUDIT LOGS
            print(f"Manual Aadhaar: {m_clean}")
            print(f"OCR Aadhaar: {o_clean}")
            
            if m_clean != o_clean:
                self._errors = {}
                raise ValidationError("Identity verification failed: Aadhaar number does not match the uploaded document.")

        # 1.3 Name OCR Fuzzy-Match
        if m_full_name and self.ocr_name:
            m_name = re.sub(r'[^a-zA-Z ]', '', str(m_full_name)).lower().strip()
            o_name = re.sub(r'[^a-zA-Z ]', '', str(self.ocr_name)).lower().strip()
            similarity = SequenceMatcher(None, m_name, o_name).ratio()
            
            if similarity < 0.8:
                self._errors = {}
                raise ValidationError("Identity verification failed: Name does not match the uploaded document.")

        # --- STEP 2: DATABASE UNIQUENESS (ONLY IF IDENTITY PASSES) ---
        
        username = self.cleaned_data.get("username")
        email = self.cleaned_data.get("email")

        # 2.1 Username Check
        if username:
            u_exists = User.objects.filter(username=username).exists()
            print(f"Username exists: {u_exists}")
            if u_exists:
                self.add_error('username', "Username already exists.")

        # 2.2 Email Check
        if email:
            e_exists = User.objects.filter(email=email).exists()
            print(f"Email exists: {e_exists}")
            if e_exists:
                self.add_error('email', "Email already exists.")

        # 2.3 Aadhaar Duplicate Check
        if m_clean and UserProfile.objects.filter(aadhaar_number=m_clean).exists():
            self.add_error('aadhaar_number', "This Aadhaar is already registered.")

        # --- STEP 3: CREDENTIAL SECURITY ---
        pwd = self.cleaned_data.get("password")
        cnf = self.cleaned_data.get("confirm_password")
        if pwd and cnf and pwd != cnf:
            self.add_error('confirm_password', "Passwords do not match.")

        return self.cleaned_data

        pwd = self.cleaned_data.get("password")
        cnf = self.cleaned_data.get("confirm_password")
        if pwd and cnf and pwd != cnf:
            self.add_error('confirm_password', "Passwords do not match.")

        return self.cleaned_data







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


class StaffCreationForm(forms.ModelForm):
    """
    Secure form for Admins to create Staff users.
    Role/Status fields are EXCLUDED to prevent frontend tampering.
    """
    full_name = forms.CharField(
        max_length=255, 
        min_length=3,
        required=True, 
        label="Staff Full Name",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter staff member full name'})
    )

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        min_length=8,
        label="Set Initial Password"
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label="Confirm Password"
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'phone']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Email is already registered.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm = cleaned_data.get("confirm_password")

        if password and confirm and password != confirm:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned_data