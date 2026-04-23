from decimal import Decimal


def usd(amount: Decimal) -> str:
    return f"${Decimal(amount):,.2f}"
