from django import template
import os

register = template.Library()


@register.filter
def filename(value):
    if not value:
        return ""
    try:
        return os.path.basename(value.name)
    except Exception:
        return os.path.basename(str(value))


@register.filter
def replace(value, arg):
    """
    Usage: {{ value|replace:"_, " }} (replaces first char before comma with second char)
    """
    if not isinstance(value, str):
        return value
    if ',' in arg:
        old, new = arg.split(',', 1)
        return value.replace(old, new)
    return value


@register.filter
def subtract(value, arg):
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter(name='abs')
def absolute(value):
    try:
        return abs(float(value))
    except (ValueError, TypeError):
        return 0


@register.filter
def multiply(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0
