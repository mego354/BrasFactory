from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def currency_egp(value):
    """Format a number as Egyptian Pounds."""
    try:
        return f"{float(value):,.2f} ج.م"
    except (TypeError, ValueError):
        return "0.00 ج.م"


@register.simple_tag
def progress_bar(value, max_value, css_class='bg-purple-600'):
    """Render an HTML progress bar."""
    try:
        pct = min(100, int((float(value) / float(max_value)) * 100)) if float(max_value) > 0 else 0
    except (TypeError, ValueError, ZeroDivisionError):
        pct = 0
    color_map = {
        'bg-purple-600': '#7c3aed',
        'bg-green-500': '#22c55e',
        'bg-blue-500': '#3b82f6',
        'bg-orange-500': '#f97316',
    }
    color = color_map.get(css_class, '#7c3aed')
    return mark_safe(
        f'<div class="w-full bg-gray-200 rounded-full h-2 overflow-hidden">'
        f'<div class="h-2 rounded-full transition-all duration-500" '
        f'style="width:{pct}%;background-color:{color}"></div>'
        f'</div>'
        f'<span class="text-xs text-gray-500 mt-1 block">{pct}%</span>'
    )


@register.filter
def status_badge(is_active):
    """Render an active/inactive badge."""
    if is_active:
        return mark_safe(
            '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium '
            'bg-green-100 text-green-800">نشط</span>'
        )
    return mark_safe(
        '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium '
        'bg-red-100 text-red-800">غير نشط</span>'
    )


@register.filter
def ar_number(value):
    """Format large numbers with Arabic-friendly comma separation."""
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


@register.filter
def completion_color(pct):
    """Return a Tailwind color class based on completion percentage."""
    try:
        p = float(pct)
    except (TypeError, ValueError):
        return 'text-gray-500'
    if p >= 100:
        return 'text-green-600'
    if p >= 75:
        return 'text-blue-600'
    if p >= 50:
        return 'text-yellow-600'
    return 'text-red-600'


@register.filter
def subtract(value, arg):
    try:
        return float(value) - float(arg)
    except (TypeError, ValueError):
        return 0


@register.filter
def percentage(value, total):
    try:
        return round((float(value) / float(total)) * 100, 1) if float(total) > 0 else 0
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


@register.filter
def get_item(dictionary, key):
    """Access dict value by key in templates: {{ mydict|get_item:key }}"""
    if dictionary is None:
        return None
    return dictionary.get(str(key))


@register.filter
def qr_code_base64(data):
    """Generates a data URI base64 PNG image of a QR code."""
    if not data:
        return ''
    import io
    import base64
    import qrcode
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=5,
        border=1,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{b64}"
