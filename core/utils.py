import calendar
from django.utils import timezone


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
