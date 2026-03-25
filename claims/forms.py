from django import forms
from .models import ClaimNote, ClaimAssessment


class ClaimNoteForm(forms.ModelForm):
    """
    Form for creating and editing claim notes with role-based functionality.
    """
    
    class Meta:
        model = ClaimNote
        fields = ['note_type', 'message', 'is_important']
        widgets = {
            'note_type': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_note_type'
            }),
            'message': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Enter your note here...',
                'id': 'id_message'
            }),
            'is_important': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id': 'id_is_important'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add custom styling and help text
        self.fields['note_type'].help_text = """
        <div class="text-muted small">
            <strong>Customer Note:</strong> Visible to Policyholder, Staff, and Admin<br>
            <strong>Internal Note:</strong> Visible only to Staff and Admin
        </div>
        """
        self.fields['is_important'].label = "Mark as Important"


class StaffNoteForm(ClaimNoteForm):
    """
    Enhanced form for staff members with additional validation and features.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Staff can create both types of notes
        self.fields['note_type'].choices = ClaimNote.NOTE_TYPE
        
    def clean_message(self):
        message = self.cleaned_data.get('message')
        if message and len(message.strip()) < 5:
            raise forms.ValidationError("Note message must be at least 5 characters long.")
        return message


class CustomerNoteForm(ClaimNoteForm):
    """
    Form for customer notes (if needed in future - currently only staff can create notes).
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Customers can only create customer notes
        self.fields['note_type'].choices = [('customer', 'Customer Note')]
        self.fields['note_type'].widget.attrs['disabled'] = True


class ClaimAssessmentForm(forms.ModelForm):
    """
    Form for Claim Assessment with auto calculation of recommended_amount.
    The recommended_amount field is readonly and calculated automatically.
    """
    
    class Meta:
        model = ClaimAssessment
        fields = ['verdict', 'bill_amount', 'coverage', 'deductible', 'recommended_amount', 'remarks', 'investigation_required']
        widgets = {
            'verdict': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_verdict'
            }),
            'bill_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': 'Enter bill amount...',
                'id': 'id_bill_amount'
            }),
            'coverage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': 'Enter coverage percentage (e.g., 80.00)...',
                'id': 'id_coverage'
            }),
            'deductible': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': 'Enter deductible amount...',
                'id': 'id_deductible'
            }),
            'recommended_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'readonly': 'readonly',
                'placeholder': 'Auto-calculated...',
                'id': 'id_recommended_amount'
            }),
            'remarks': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Enter assessment remarks...',
                'id': 'id_remarks'
            }),
            'investigation_required': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id': 'id_investigation_required'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make recommended_amount readonly
        self.fields['recommended_amount'].widget.attrs['readonly'] = True
        self.fields['recommended_amount'].widget.attrs['style'] = 'background-color: #f8f9fa; cursor: not-allowed;'
        
        # Add help text for calculation
        self.fields['bill_amount'].help_text = "Total bill amount from medical/hospital documents"
        self.fields['coverage'].help_text = "Coverage percentage (e.g., 80.00 for 80%)"
        self.fields['deductible'].help_text = "Deductible amount to be subtracted"
        self.fields['recommended_amount'].help_text = "Auto-calculated using formula: (bill_amount × coverage ÷ 100) - deductible"
    
    def clean(self):
        cleaned_data = super().clean()
        bill_amount = cleaned_data.get('bill_amount')
        coverage = cleaned_data.get('coverage')
        deductible = cleaned_data.get('deductible')
        
        # Validate that if bill_amount and coverage are provided, they should be positive
        if bill_amount is not None and bill_amount < 0:
            raise forms.ValidationError("Bill amount cannot be negative.")
        
        if coverage is not None and (coverage < 0 or coverage > 100):
            raise forms.ValidationError("Coverage percentage must be between 0 and 100.")
        
        if deductible is not None and deductible < 0:
            raise forms.ValidationError("Deductible amount cannot be negative.")
        
        return cleaned_data
