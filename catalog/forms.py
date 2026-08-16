from django import forms
from .models import Color, Size, Client, ProductionStage, ProductModel, ProductModelStage, ProductVariant


class ColorForm(forms.ModelForm):
    class Meta:
        model = Color
        fields = ['name', 'is_active']
        labels = {'name': 'اسم اللون', 'is_active': 'نشط'}
        widgets = {'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: أسود'})}


class SizeForm(forms.ModelForm):
    class Meta:
        model = Size
        fields = ['name', 'sort_order', 'is_active']
        labels = {'name': 'المقاس', 'sort_order': 'الترتيب', 'is_active': 'نشط'}
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: M'}),
            'sort_order': forms.NumberInput(attrs={'class': 'form-control'}),
        }


class ProductionStageForm(forms.ModelForm):
    class Meta:
        model = ProductionStage
        fields = ['name', 'description', 'sort_order', 'is_active']
        labels = {
            'name': 'اسم المرحلة', 'description': 'الوصف',
            'sort_order': 'الترتيب', 'is_active': 'نشط'
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'sort_order': forms.NumberInput(attrs={'class': 'form-control'}),
        }


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['code', 'name', 'phone', 'is_active']
        labels = {
            'code': 'كود العميل', 'name': 'اسم العميل',
            'phone': 'رقم الهاتف', 'is_active': 'نشط'
        }
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: CLT-001'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '01xxxxxxxxx'}),
        }


# ─── Wizard Forms ─────────────────────────────────────────────

class ModelStep1Form(forms.ModelForm):
    """Step 1: Basic model info."""
    class Meta:
        model = ProductModel
        fields = ['code', 'name', 'client', 'description']
        labels = {
            'code': 'كود الموديل', 'name': 'اسم الموديل',
            'client': 'العميل', 'description': 'الوصف'
        }
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: BR-100'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'client': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class ModelStep2Form(forms.Form):
    """Step 2: Color selection."""
    colors = forms.ModelMultipleChoiceField(
        queryset=Color.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple,
        label='الألوان',
        error_messages={'required': 'يجب اختيار لون واحد على الأقل.'}
    )


class ModelStep3Form(forms.Form):
    """Step 3: Size selection."""
    sizes = forms.ModelMultipleChoiceField(
        queryset=Size.objects.filter(is_active=True).order_by('sort_order'),
        widget=forms.CheckboxSelectMultiple,
        label='المقاسات',
        error_messages={'required': 'يجب اختيار مقاس واحد على الأقل.'}
    )


class ModelStageInlineForm(forms.Form):
    """Single stage + price row in step 4."""
    stage_id = forms.IntegerField(widget=forms.HiddenInput)
    selected = forms.BooleanField(required=False)
    unit_price = forms.DecimalField(
        max_digits=10, decimal_places=2, required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'})
    )
    sort_order = forms.IntegerField(
        required=False, initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'style': 'width:70px'})
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('selected') and not cleaned.get('unit_price'):
            raise forms.ValidationError('أدخل سعر الوحدة للمرحلة المختارة.')
        return cleaned


class ProductVariantPlanForm(forms.ModelForm):
    """Update planned quantity for a variant."""
    class Meta:
        model = ProductVariant
        fields = ['planned_quantity']
        widgets = {
            'planned_quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'})
        }
