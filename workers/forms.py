from django import forms
from .models import Worker
from catalog.models import ProductionStage


class WorkerForm(forms.ModelForm):
    stages = forms.ModelMultipleChoiceField(
        queryset=ProductionStage.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='المراحل المسندة'
    )

    class Meta:
        model = Worker
        fields = ['name', 'phone', 'stages', 'is_active', 'notes']
        labels = {
            'name': 'اسم العامل',
            'phone': 'رقم الهاتف',
            'is_active': 'نشط',
            'notes': 'ملاحظات',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '01xxxxxxxxx'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
