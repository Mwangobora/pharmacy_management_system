from __future__ import annotations


def build_metric_payload(current_value, previous_value, *, allow_change=True):
    current = float(current_value or 0)
    previous = float(previous_value or 0)
    payload = {
        'value': current,
        'previous_value': previous,
        'absolute_change': current - previous,
        'percentage_change': None,
        'comparison_available': False,
    }

    if not allow_change:
        return payload

    if previous == 0:
        return payload

    payload['comparison_available'] = True
    payload['percentage_change'] = ((current - previous) / abs(previous)) * 100
    return payload

