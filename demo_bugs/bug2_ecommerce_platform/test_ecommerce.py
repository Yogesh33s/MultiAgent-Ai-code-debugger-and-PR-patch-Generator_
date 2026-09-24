import pytest
from ecommerce_platform import (
    Product, Customer, OrderItem, Address, Order,
    PricingEngine, InventoryService, ShippingService, PaymentGateway, OrderService
)


def test_product_margin():
    prod = Product(
        product_id="prod_01",
        sku="SKU-PHONE-01",
        name="Smartphone",
        category="Electronics",
        base_price=500.0,
        cost_price=300.0,
        weight_kg=0.5
    )
    assert prod.calculate_margin() == 200.0


def test_tiered_tax_progressive_luxury_surcharge():
    """
    Test progressive luxury tax calculation on a $2,000 purchase in California (CA).
    CA base rate: 7.25% (0.0725)
    
    Expected Calculation:
    - Tier 1 ($0 - $1,000) @ 7.25% = $72.50
    - Tier 2 ($1,000 - $2,000) @ (7.25% + 2% luxury surcharge = 9.25%) = $92.50
    Total expected tax = $72.50 + $92.50 = $165.00
    
    Current buggy behavior:
    - Tier 2 subtracts 2% (5.25%), yielding $52.50, totaling $125.00 instead of $165.00!
    """
    engine = PricingEngine()
    tax = engine.calculate_tiered_tax(2000.0, "CA")
    assert tax == 165.00, f"Expected luxury surcharge tax of $165.00, got ${tax}"
