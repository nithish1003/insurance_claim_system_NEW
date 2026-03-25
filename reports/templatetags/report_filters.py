from django import template

register = template.Library()

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
