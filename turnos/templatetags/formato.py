from django import template

register = template.Library()


@register.filter
def clp(valor):
    """Formatea un monto en pesos chilenos: 12000 -> $12.000"""
    if valor is None or valor == "":
        return "—"
    return "$" + f"{int(valor):,}".replace(",", ".")


@register.filter
def absoluto(valor):
    return abs(valor)
