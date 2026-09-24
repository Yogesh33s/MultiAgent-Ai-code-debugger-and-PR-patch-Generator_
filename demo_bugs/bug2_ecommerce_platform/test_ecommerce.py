import pytest
from ecommerce_platform import (
    Product,
    Customer,
    OrderItem,
    InventoryManager,
    PricingEngine,
    OrderService,
)


def test_subtotal_calculation():
    engine = PricingEngine()
    items = [
        OrderItem(sku="SKU-1", name="Keyboard", unit_price=45.0, quantity=2),
        OrderItem(sku="SKU-2", name="Mouse", unit_price=20.0, quantity=1),
    ]
    assert engine.calculate_subtotal(items) == 110.0


def test_silver_tier_discount():
    engine = PricingEngine()
    # 5% discount on $100 subtotal should be $5.00
    discount = engine.calculate_tier_discount(100.0, "silver")
    assert discount == 5.0


def test_gold_tier_discount():
    engine = PricingEngine()
    # Gold tier gets 15% discount.
    # On $100 subtotal, discount MUST be $15.00.
    discount = engine.calculate_tier_discount(100.0, "gold")
    assert discount == 15.0, f"Expected $15.00 discount for gold tier, but got ${discount}"


def test_platinum_tier_discount():
    engine = PricingEngine()
    # 25% discount on $100 subtotal should be $25.00
    discount = engine.calculate_tier_discount(100.0, "platinum")
    assert discount == 25.0
