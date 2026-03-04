import pytest

from shop import RULE_ORDER, price_cart


def _base_customer():
    return {"id_client": "C1", "loyalty_level": "basic"}


def _item(sku="A", name="Prod", category="books", unit_price_gross=30.0, vat_rate=0.23, qty=1):
    return {
        "sku": sku,
        "name": name,
        "category": category,
        "unit_price_gross": unit_price_gross,
        "vat_rate": vat_rate,
        "qty": qty,
    }


def test_rule_order_is_exposed_and_stable():
    out = price_cart([_item()], _base_customer(), [])
    assert out["rule_order"] == RULE_ORDER


def test_validation_rejects_empty_cart():
    with pytest.raises(ValueError):
        price_cart([], _base_customer(), [])


def test_category_percent_discount_applies():
    promos = [{"type": "category_percent", "category": "books", "percent": 0.10}]
    out = price_cart([_item(unit_price_gross=100, qty=1)], _base_customer(), promos)
    assert out["lines"][0]["discount_gross"] == 10.0
    assert out["lines"][0]["price_after_gross"] == 90.0


def test_outlet_excluded_from_percent_discount():
    promos = [{"type": "category_percent", "category": "outlet", "percent": 0.50}]
    out = price_cart([_item(category="outlet", unit_price_gross=100)], _base_customer(), promos)
    assert out["lines"][0]["discount_gross"] == 0.0


def test_buy2get1_qty_2():
    promos = [{"type": "buy2get1_sku", "sku": "A"}]
    out = price_cart([_item(qty=2, unit_price_gross=20)], _base_customer(), promos)
    assert out["lines"][0]["discount_gross"] == 0.0


def test_buy2get1_qty_3():
    promos = [{"type": "buy2get1_sku", "sku": "A"}]
    out = price_cart([_item(qty=3, unit_price_gross=20)], _base_customer(), promos)
    assert out["lines"][0]["discount_gross"] == 20.0


def test_buy2get1_qty_4():
    promos = [{"type": "buy2get1_sku", "sku": "A"}]
    out = price_cart([_item(qty=4, unit_price_gross=20)], _base_customer(), promos)
    assert out["lines"][0]["discount_gross"] == 20.0


def test_coupon_not_combined_with_buy2get1():
    promos = [
        {"type": "buy2get1_sku", "sku": "A"},
        {"type": "cart_coupon_amount", "amount": 10, "min_cart": 1},
    ]
    out = price_cart([_item(qty=3, unit_price_gross=20)], _base_customer(), promos)
    assert out["lines"][0]["discount_gross"] == 10.0


def test_coupon_min_cart_threshold():
    promos = [{"type": "cart_coupon_amount", "amount": 20, "min_cart": 200}]
    out = price_cart([_item(unit_price_gross=50, qty=1)], _base_customer(), promos)
    assert out["lines"][0]["discount_gross"] == 0.0


def test_free_shipping_threshold_edge():
    promos = [{"type": "free_shipping_threshold", "threshold": 200}]
    out = price_cart([_item(unit_price_gross=200, qty=1)], _base_customer(), promos, shipping_base=15)
    assert out["summary"]["shipping_cost"] == 0.0


def test_cheapest_product_half_price_in_category():
    cart = [
        _item(sku="A", unit_price_gross=100, qty=1, category="games"),
        _item(sku="B", unit_price_gross=40, qty=1, category="games"),
    ]
    promos = [{"type": "cheapest_half_category", "category": "games"}]
    out = price_cart(cart, _base_customer(), promos)
    by_sku = {l["sku"]: l for l in out["lines"]}
    assert by_sku["B"]["discount_gross"] == 20.0
    assert by_sku["A"]["discount_gross"] == 0.0


def test_price_never_below_one_zloty_per_unit():
    promos = [
        {"type": "category_percent", "category": "books", "percent": 0.9},
        {"type": "cart_coupon_amount", "amount": 100, "min_cart": 1},
    ]
    out = price_cart([_item(unit_price_gross=2, qty=3, category="books")], _base_customer(), promos)
    assert out["lines"][0]["price_after_gross"] >= 3.0


def test_summary_contains_gross_net_vat_shipping_and_savings():
    out = price_cart([_item(unit_price_gross=100, qty=1)], _base_customer(), [], shipping_base=15)
    summary = out["summary"]
    assert set(summary) == {"gross_total", "net_total", "vat_total", "shipping_cost", "total_to_pay", "savings"}
    assert summary["gross_total"] == 100.0
    assert summary["shipping_cost"] == 15.0
    assert summary["total_to_pay"] == 115.0
