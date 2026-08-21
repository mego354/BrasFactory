import calendar
from datetime import date
from django.utils import timezone


ARABIC_MONTHS = [
    '', 'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
    'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'
]


def get_current_month_date_range(start_date=None, end_date=None):
    """
    Returns (start_date, end_date) as 'YYYY-MM-DD' strings.
    If start_date is not provided or empty, defaults to the 1st day of the current month.
    If end_date is not provided or empty, defaults to the last day of the current month.
    """
    today = timezone.localdate()

    if not start_date or not str(start_date).strip():
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
    else:
        start_date = str(start_date).strip()

    if not end_date or not str(end_date).strip():
        _, last_day_num = calendar.monthrange(today.year, today.month)
        last_day = today.replace(day=last_day_num)
        end_date = last_day.strftime('%Y-%m-%d')
    else:
        end_date = str(end_date).strip()

    return start_date, end_date


def get_month_navigation_context(year=None, month=None):
    """Generate calendar navigation metadata and date boundaries for month-based reporting."""
    today = timezone.localdate()
    try:
        y = int(year) if year else today.year
        m = int(month) if month else today.month
    except (ValueError, TypeError):
        y, m = today.year, today.month

    if m < 1 or m > 12:
        m = today.month

    _, num_days = calendar.monthrange(y, m)
    start_date = date(y, m, 1)
    end_date = date(y, m, num_days)

    if m == 1:
        prev_year, prev_month = y - 1, 12
    else:
        prev_year, prev_month = y, m - 1

    if m == 12:
        next_year, next_month = y + 1, 1
    else:
        next_year, next_month = y, m + 1

    if today.month == 1:
        last_month_year, last_month_month = today.year - 1, 12
    else:
        last_month_year, last_month_month = today.year, today.month - 1

    return {
        'selected_year': y,
        'selected_month': m,
        'month_name': ARABIC_MONTHS[m],
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'prev_year': prev_year,
        'prev_month': prev_month,
        'next_year': next_year,
        'next_month': next_month,
        'this_year': today.year,
        'this_month': today.month,
        'last_month_year': last_month_year,
        'last_month_month': last_month_month,
        'is_current_month': (y == today.year and m == today.month),
        'is_last_month': (y == last_month_year and m == last_month_month),
    }
