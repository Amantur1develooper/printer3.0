from django import forms
from django.conf import settings
from .models import Order


class UploadForm(forms.Form):
    customer_name = forms.CharField(
        label='Ваше имя',
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Иван',
            'autocomplete': 'given-name',
        }),
    )
    customer_phone = forms.CharField(
        label='Номер телефона',
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': '+996 700 000000',
            'type': 'tel',
            'autocomplete': 'tel',
        }),
    )
    customer_comment = forms.CharField(
        label='Комментарий',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Особые пожелания (необязательно)',
        }),
    )
    file = forms.FileField(
        label='PDF-файл',
        widget=forms.ClearableFileInput(attrs={
            'accept': '.pdf',
            'class': 'form-control',
            'id': 'fileInput',
        }),
    )

    def clean_file(self):
        f = self.cleaned_data['file']
        max_mb = getattr(settings, 'MAX_FILE_SIZE_MB', 50)
        if f.size > max_mb * 1024 * 1024:
            raise forms.ValidationError(f'Файл слишком большой. Максимум {max_mb} МБ.')
        if not f.name.lower().endswith('.pdf'):
            raise forms.ValidationError('Принимаются только PDF-файлы.')
        return f


class ConfigureForm(forms.Form):
    copies = forms.IntegerField(
        label='Количество копий',
        min_value=1,
        max_value=100,
        initial=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_copies'}),
    )
    color = forms.ChoiceField(
        label='Цвет печати',
        choices=[('bw', 'Чёрно-белая'), ('color', 'Цветная')],
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_color'}),
    )
    duplex = forms.ChoiceField(
        label='Тип печати',
        choices=[('false', 'Односторонняя'), ('true', 'Двусторонняя')],
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_duplex'}),
    )
    paper_format = forms.ChoiceField(
        label='Формат бумаги',
        choices=[('A4', 'A4')],
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_paper_format'}),
    )
    page_range = forms.CharField(
        label='Диапазон страниц',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Например: 1-5,7,9-12 (пусто = все)',
            'id': 'id_page_range',
        }),
    )
    orientation = forms.ChoiceField(
        label='Ориентация',
        choices=Order.ORIENTATION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    even_only = forms.BooleanField(
        label='Только чётные страницы',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_even_only'}),
    )
    odd_only = forms.BooleanField(
        label='Только нечётные страницы',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_odd_only'}),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('even_only') and cleaned.get('odd_only'):
            raise forms.ValidationError('Нельзя выбрать одновременно только чётные и только нечётные страницы.')
        return cleaned


class ReceiptUploadForm(forms.Form):
    payment_receipt = forms.ImageField(
        label='Фото или скриншот чека',
        widget=forms.ClearableFileInput(attrs={
            'accept': 'image/*',
            'capture': 'environment',
            'class': 'form-control',
        }),
    )
    transaction_id = forms.CharField(
        label='Номер транзакции (если есть)',
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Необязательно'}),
    )
