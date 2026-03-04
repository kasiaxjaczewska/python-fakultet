from __future__ import annotations

from typing import Any


RULE_ORDER = [
    "category_percent",
    "cheapest_half_category",
    "buy2get1_sku",
    "cart_coupon_amount",
    "free_shipping_threshold",
]


REQUIRED_ITEM_KEYS = {"sku", "name", "category", "unit_price_gross", "vat_rate", "qty"}


def _round2(value: float) -> float:
    return round(float(value) + 1e-9, 2)


def _validate_input(cart: list[dict[str, Any]], customer: dict[str, Any], promotions: list[dict[str, Any]]) -> None:
    if not isinstance(cart, list) or not cart:
        raise ValueError("cart must be a non-empty list")
    if not isinstance(customer, dict):
        raise ValueError("customer must be a dict")
    if not isinstance(promotions, list):
        raise ValueError("promotions must be a list")

    for item in cart:
        if not isinstance(item, dict):
            raise ValueError("each cart item must be a dict")
        missing = REQUIRED_ITEM_KEYS - set(item)
        if missing:
            raise ValueError(f"missing item keys: {sorted(missing)}")
        if item["qty"] <= 0:
            raise ValueError("qty must be > 0")
        if item["unit_price_gross"] <= 0:
            raise ValueError("unit_price_gross must be > 0")
        if not (0 <= item["vat_rate"] <= 1):
            raise ValueError("vat_rate must be between 0 and 1")


def _cap_discount(line: dict[str, Any], amount: float) -> float:
    floor_total = line["qty"] * 1.0
    max_discount = max(0.0, line["base_gross"] - line["discount_gross"] - floor_total)
    return min(max(0.0, amount), max_discount)


def _apply_category_percent(lines: list[dict[str, Any]], promotions: list[dict[str, Any]]) -> None:
    promos = [p for p in promotions if p.get("type") == "category_percent"]
    for promo in promos:
        category = promo["category"]
        percent = float(promo["percent"])
        for line in lines:
            if line["category"] == category and line["category"] != "outlet":
                amount = (line["base_gross"] - line["discount_gross"]) * percent
                line["discount_gross"] += _cap_discount(line, amount)


def _apply_cheapest_half(lines: list[dict[str, Any]], promotions: list[dict[str, Any]]) -> None:
    promos = [p for p in promotions if p.get("type") == "cheapest_half_category"]
    for promo in promos:
        category = promo["category"]
        eligible = [l for l in lines if l["category"] == category and l["category"] != "outlet"]
        if not eligible:
            continue
        cheapest = min(eligible, key=lambda l: l["unit_price_gross"])
        amount = 0.5 * cheapest["unit_price_gross"]
        cheapest["discount_gross"] += _cap_discount(cheapest, amount)


def _apply_buy2get1(lines: list[dict[str, Any]], promotions: list[dict[str, Any]], coupon_present: bool) -> None:
    if coupon_present:
        return
    promos = [p for p in promotions if p.get("type") == "buy2get1_sku"]
    for promo in promos:
        sku = promo["sku"]
        for line in lines:
            if line["sku"] == sku:
                free_units = line["qty"] // 3
                amount = free_units * line["unit_price_gross"]
                line["discount_gross"] += _cap_discount(line, amount)


def _apply_coupon(lines: list[dict[str, Any]], promotions: list[dict[str, Any]]) -> float:
    coupon_promos = [p for p in promotions if p.get("type") == "cart_coupon_amount"]
    if not coupon_promos:
        return 0.0

    promo = coupon_promos[0]
    amount = float(promo["amount"])
    min_cart = float(promo.get("min_cart", 0))
    current_total = sum(l["base_gross"] - l["discount_gross"] for l in lines)
    if current_total < min_cart:
        return 0.0

    total = current_total
    if total <= 0:
        return 0.0

    to_apply = min(amount, total)
    for i, line in enumerate(lines):
        line_total = line["base_gross"] - line["discount_gross"]
        if i == len(lines) - 1:
            line_part = to_apply
        else:
            line_part = _round2(to_apply * (line_total / total))
        real_part = _cap_discount(line, line_part)
        line["discount_gross"] += real_part
        to_apply = _round2(to_apply - real_part)

    return amount


def _shipping_cost(lines: list[dict[str, Any]], promotions: list[dict[str, Any]], base_shipping: float) -> float:
    cost = float(base_shipping)
    promos = [p for p in promotions if p.get("type") == "free_shipping_threshold"]
    if not promos:
        return _round2(cost)

    threshold = float(promos[0]["threshold"])
    total = sum(l["base_gross"] - l["discount_gross"] for l in lines)
    if total >= threshold:
        return 0.0
    return _round2(cost)


def price_cart(
    cart: list[dict[str, Any]],
    customer: dict[str, Any],
    promotions: list[dict[str, Any]],
    shipping_base: float = 15.0,
) -> dict[str, Any]:
    _validate_input(cart, customer, promotions)

    lines: list[dict[str, Any]] = []
    for item in cart:
        base = float(item["unit_price_gross"]) * int(item["qty"])
        lines.append(
            {
                "sku": item["sku"],
                "name": item["name"],
                "category": item["category"],
                "qty": int(item["qty"]),
                "vat_rate": float(item["vat_rate"]),
                "unit_price_gross": float(item["unit_price_gross"]),
                "base_gross": _round2(base),
                "discount_gross": 0.0,
            }
        )

    coupon_present = any(p.get("type") == "cart_coupon_amount" for p in promotions)

    _apply_category_percent(lines, promotions)
    _apply_cheapest_half(lines, promotions)
    _apply_buy2get1(lines, promotions, coupon_present=coupon_present)
    _apply_coupon(lines, promotions)

    shipping = _shipping_cost(lines, promotions, shipping_base)

    line_receipt: list[dict[str, Any]] = []
    gross_total = 0.0
    net_total = 0.0
    vat_total = 0.0

    for line in lines:
        before = _round2(line["base_gross"])
        discount = _round2(line["discount_gross"])
        after = _round2(before - discount)
        net = _round2(after / (1 + line["vat_rate"]))
        vat = _round2(after - net)
        gross_total += after
        net_total += net
        vat_total += vat
        line_receipt.append(
            {
                "sku": line["sku"],
                "name": line["name"],
                "qty": line["qty"],
                "price_before_gross": before,
                "discount_gross": discount,
                "price_after_gross": after,
                "vat_rate": line["vat_rate"],
            }
        )

    gross_total = _round2(gross_total)
    net_total = _round2(net_total)
    vat_total = _round2(vat_total)
    total_with_shipping = _round2(gross_total + shipping)
    savings = _round2(sum(l["discount_gross"] for l in line_receipt) + (shipping_base - shipping))

    return {
        "rule_order": RULE_ORDER,
        "customer": customer,
        "lines": line_receipt,
        "summary": {
            "gross_total": gross_total,
            "net_total": net_total,
            "vat_total": vat_total,
            "shipping_cost": _round2(shipping),
            "total_to_pay": total_with_shipping,
            "savings": _round2(savings),
        },
    }
