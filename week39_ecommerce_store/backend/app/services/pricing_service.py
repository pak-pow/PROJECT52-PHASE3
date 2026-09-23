FREE_SHIPPING_THRESHOLD_CENTS = 5000
FLAT_SHIPPING_CENTS = 699
TAX_RATE = 0.0825

PROMO_CODES = {
    "DISCOUNT10": {
        "description": "10% off subtotal",
        "type": "percentage",
        "value": 0.10,
        "min_subtotal_cents": 0,
    },
    "SAVE20": {
        "description": "20% off orders over $100",
        "type": "percentage",
        "value": 0.20,
        "min_subtotal_cents": 10000,
    },
    "FREESHIP": {
        "description": "Free standard shipping",
        "type": "shipping",
        "value": 1.0,
        "min_subtotal_cents": 0,
    },
}


def format_cents(cents):
    return f"${cents / 100:.2f}"


def validate_promo_code(promo_code, subtotal_cents=0):
    if not promo_code:
        return True, None

    code = promo_code.strip().upper()
    rule = PROMO_CODES.get(code)
    if not rule:
        return False, f"Promo code '{promo_code}' is invalid."

    if subtotal_cents < rule["min_subtotal_cents"]:
        min_fmt = format_cents(rule["min_subtotal_cents"])
        return False, f"Promo code '{code}' requires a minimum subtotal of {min_fmt}."

    return True, None


def calculate_pricing(items, promo_code=None):
    subtotal_cents = sum(
        item["price_cents"] * item["quantity"]
        for item in items
        if "price_cents" in item
    )

    discount_cents = 0
    valid_promo = None

    if promo_code:
        clean_code = promo_code.strip().upper()
        is_valid, _ = validate_promo_code(clean_code, subtotal_cents)
        if is_valid:
            valid_promo = clean_code
            rule = PROMO_CODES[clean_code]
            if rule["type"] == "percentage":
                discount_cents = round(subtotal_cents * rule["value"])

    if subtotal_cents == 0:
        shipping_cents = 0
    elif valid_promo == "FREESHIP" or subtotal_cents >= FREE_SHIPPING_THRESHOLD_CENTS:
        shipping_cents = 0
    else:
        shipping_cents = FLAT_SHIPPING_CENTS

    subtotal_after_discount = max(0, subtotal_cents - discount_cents)

    if subtotal_after_discount > 0:
        tax_cents = round(subtotal_after_discount * TAX_RATE)
    else:
        tax_cents = 0

    total_cents = subtotal_after_discount + shipping_cents + tax_cents
    total_qty = sum(item.get("quantity", 0) for item in items)

    return {
        "subtotal_cents": subtotal_cents,
        "subtotal_formatted": format_cents(subtotal_cents),
        "discount_cents": discount_cents,
        "discount_formatted": format_cents(discount_cents),
        "promo_code": valid_promo,
        "shipping_cents": shipping_cents,
        "shipping_formatted": format_cents(shipping_cents),
        "tax_cents": tax_cents,
        "tax_formatted": format_cents(tax_cents),
        "total_cents": total_cents,
        "total_formatted": format_cents(total_cents),
        "item_count": total_qty,
        "free_shipping_eligible": subtotal_cents >= FREE_SHIPPING_THRESHOLD_CENTS,
        "free_shipping_threshold_cents": FREE_SHIPPING_THRESHOLD_CENTS,
    }
