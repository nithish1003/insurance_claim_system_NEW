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

    def clean_aadhaar_number(self):
        """🛡️ UX: Automatically strip spaces/dashes for the user."""
        data = self.cleaned_data['aadhaar_number']
        return "".join(filter(str.isdigit, str(data)))

    def clean(self):
        print("FORM CLEAN HIT")
        cleaned_data = super().clean()
        full_name = cleaned_data.get("full_name")
        aadhaar_number = cleaned_data.get("aadhaar_number")
        id_proof = cleaned_data.get("id_proof")
        
        if full_name and aadhaar_number and id_proof:
            import os
            import tempfile
            from ai_features.services.ocr_engine import extract_text_compat
            from ai_features.services.kyc_verification_service import verify_aadhaar_document
            from ai_features.services.ocr_service import verify_aadhaar, get_ocr_engine
            
            # Ensure OCR is ready (Lazy Load)
            ocr = get_ocr_engine()
            
            # Windows-compatible temp file handling
            temp_suffix = os.path.splitext(id_proof.name)[1]
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=temp_suffix)
            try:
                for chunk in id_proof.chunks():
                    tf.write(chunk)
                tf.close()
                
                # Call Enterprise KYC service
                from ai_features.services.kyc_verification_service import verify_aadhaar_document
                result = verify_aadhaar_document(tf.name, full_name, aadhaar_number)
                
                # Step 2: Store results temporarily for view usage
                # 1. Store result for View-Layer persistence (MVC Separation)
                self.kyc_result = result
                self.kyc_result["filename"] = os.path.basename(tf.name)
                self.kyc_result["submitted_name"] = full_name
                self.kyc_result["submitted_number"] = "".join(filter(str.isdigit, str(aadhaar_number)))

                if result.get("reason_code"):
                    user_msg = result.get("user_message", "Identity verification failed. Please check your document.")
                    reason_code = result.get("reason_code")
                    
                    # Requirement 1: Only hard-fail on critical mismatches
                    if reason_code == "AADHAAR_NUMBER_MISMATCH":
                        self.add_error('aadhaar_number', user_msg)
                    elif reason_code in ["NAME_MAJOR_MISMATCH", "DOCUMENT_UNREADABLE"]:
                        self.add_error('full_name', user_msg)
                    elif result.get("verified") is False and not result.get("review_required"):
                        self.add_error('id_proof', user_msg)
                
                elif result.get("verified") is False and not result.get("review_required"):
                    self.add_error('id_proof', "Identity verification failed. Please ensure the document is a valid official Aadhaar.")
            finally:
                if os.path.exists(tf.name):
                    try: os.remove(tf.name)
                    except: pass
        
        # --- UNIQUENESS CHECKS ---
        username = cleaned_data.get("username")
        email = cleaned_data.get("email")
        
        if username and User.objects.filter(username=username).exists():
            self.add_error('username', "Username already exists.")
            
        if email and User.objects.filter(email=email).exists():
            self.add_error('email', "Email already exists.")
            
        if aadhaar_number:
            norm_aadhaar = "".join(filter(str.isdigit, str(aadhaar_number)))
            if User.objects.filter(aadhaar_number=norm_aadhaar).exists():
                self.add_error('aadhaar_number', "This Aadhaar is already registered.")

        # --- PASSWORD CHECK ---
        pwd = cleaned_data.get("password")
        cnf = cleaned_data.get("confirm_password")
        if pwd and cnf and pwd != cnf:
            self.add_error('confirm_password', "Passwords do not match.")

        return cleaned_data

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

class ReuploadIDForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['id_proof']
        widgets = {
            'id_proof': forms.FileInput(attrs={'class': 'form-control'})
        }
