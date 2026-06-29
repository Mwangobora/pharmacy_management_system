from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.utils import timezone
from rest_framework import serializers


PRESET_CHOICES = {
    'today',
    'yesterday',
    'last_7_days',
    'last_30_days',
    'this_month',
    'last_month',
    'this_quarter',
    'this_year',
    'custom',
}


@dataclass(frozen=True)
class DashboardFilters:
    preset: str
    date_from: datetime
    date_to: datetime
    comparison_date_from: datetime
    comparison_date_to: datetime
    label: str
    comparison_enabled: bool
    cashier_id: str | None
    payment_method: str | None


def _combine(day: date, start: bool) -> datetime:
    value = datetime.combine(
        day,
        time.min if start else time.max,
    )
    return timezone.make_aware(value, timezone.get_current_timezone())


def _month_bounds(today: date) -> tuple[date, date]:
    start = today.replace(day=1)
    if today.month == 12:
        next_month = today.replace(year=today.year + 1, month=1, day=1)
    else:
        next_month = today.replace(month=today.month + 1, day=1)
    return start, next_month - timedelta(days=1)


def _quarter_bounds(today: date) -> tuple[date, date]:
    quarter_start_month = ((today.month - 1) // 3) * 3 + 1
    start = today.replace(month=quarter_start_month, day=1)
    if quarter_start_month == 10:
        next_quarter = today.replace(year=today.year + 1, month=1, day=1)
    else:
        next_quarter = today.replace(month=quarter_start_month + 3, day=1)
    return start, next_quarter - timedelta(days=1)


class DashboardFilterSerializer(serializers.Serializer):
    preset = serializers.ChoiceField(
        choices=sorted(PRESET_CHOICES),
        required=False,
        default='last_7_days',
    )
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    cashier_id = serializers.CharField(required=False, allow_blank=False)
    payment_method = serializers.CharField(required=False, allow_blank=False)
    comparison = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        today = timezone.localdate()
        preset = attrs.get('preset', 'last_7_days')

        if preset == 'custom':
            if not attrs.get('date_from') or not attrs.get('date_to'):
                raise serializers.ValidationError('Custom ranges require date_from and date_to.')
            start_day = attrs['date_from']
            end_day = attrs['date_to']
        elif preset == 'today':
            start_day = end_day = today
        elif preset == 'yesterday':
            start_day = end_day = today - timedelta(days=1)
        elif preset == 'last_7_days':
            start_day = today - timedelta(days=6)
            end_day = today
        elif preset == 'last_30_days':
            start_day = today - timedelta(days=29)
            end_day = today
        elif preset == 'this_month':
            start_day, end_day = _month_bounds(today)
        elif preset == 'last_month':
            current_month_start = today.replace(day=1)
            last_month_end = current_month_start - timedelta(days=1)
            start_day, end_day = _month_bounds(last_month_end)
        elif preset == 'this_quarter':
            start_day, end_day = _quarter_bounds(today)
        elif preset == 'this_year':
            start_day = today.replace(month=1, day=1)
            end_day = today.replace(month=12, day=31)
        else:
            raise serializers.ValidationError('Unsupported preset.')

        if start_day > end_day:
            raise serializers.ValidationError('date_from cannot be after date_to.')

        comparison_span = (end_day - start_day).days + 1
        comparison_end_day = start_day - timedelta(days=1)
        comparison_start_day = comparison_end_day - timedelta(days=comparison_span - 1)

        attrs['resolved_filters'] = DashboardFilters(
            preset=preset,
            date_from=_combine(start_day, start=True),
            date_to=_combine(end_day, start=False),
            comparison_date_from=_combine(comparison_start_day, start=True),
            comparison_date_to=_combine(comparison_end_day, start=False),
            label=f'{start_day:%d %B %Y} - {end_day:%d %B %Y}',
            comparison_enabled=attrs.get('comparison', True),
            cashier_id=attrs.get('cashier_id'),
            payment_method=attrs.get('payment_method'),
        )
        return attrs

