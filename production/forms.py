from django import forms
from django.utils import timezone
from catalog.models import ProductVariant, ProductionStage
from workers.models import Worker


class ProductionEntryForm(forms.Form):
    """
    Fast production data entry form.
    Cascading dropdowns handled by AJAX — only basic fields here.
    Cross-field validation in the service layer.
    """
    variant = forms.ModelChoiceField(
        queryset=ProductVariant.objects.filter(is_active=True),
        label='نوع المنتج',
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_variant'})
    )
    stage = forms.ModelChoiceField(
        queryset=ProductionStage.objects.filter(is_active=True),
        label='المرحلة',
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_stage'})
    )
    worker = forms.ModelChoiceField(
        queryset=Worker.objects.filter(is_active=True),
        label='العامل',
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_worker'})
    )
    quantity = forms.IntegerField(
        min_value=1,
        label='الكمية',
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 'id': 'id_quantity',
            'placeholder': '0', 'min': '1'
        })
    )
    production_date = forms.DateField(
        label='تاريخ الإنتاج',
        widget=forms.DateInput(attrs={
            'class': 'form-control', 'type': 'date',
            'id': 'id_production_date'
        })
    )
    notes = forms.CharField(
        required=False,
        label='ملاحظات',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اختياري'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.localdate()
        self.fields['production_date'].initial = today

    def clean_quantity(self):
        qty = self.cleaned_data.get('quantity')
        if qty and qty < 1:
            raise forms.ValidationError('يجب أن تكون الكمية أكبر من صفر.')
        return qty


class CancelEntryForm(forms.Form):
    reason = forms.CharField(
        label='سبب الإلغاء',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'أدخل سبب الإلغاء'}),
        min_length=5
    )
