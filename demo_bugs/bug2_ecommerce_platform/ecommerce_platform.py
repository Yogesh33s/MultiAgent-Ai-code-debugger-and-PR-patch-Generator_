"""
E-Commerce Platform Core Module
Handles product inventory, customer loyalty, order pricing, tiered discounts,
tax calculations, and order fulfillment processing.
"""

from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Product:
    sku: str
    name: str
    price: float
    stock: int
    category: str
    is_active: bool = True


@dataclass
class Customer:
    customer_id: str
    name: str
    email: str
    tier: str  # 'regular', 'silver', 'gold', 'platinum'
    loyalty_points: int = 0


@dataclass
class OrderItem:
    sku: str
    name: str
    unit_price: float
    quantity: int

    @property
    def line_total(self) -> float:
        return round(self.unit_price * self.quantity, 2)


@dataclass
class Order:
    order_id: str
    customer: Customer
    items: List[OrderItem]
    subtotal: float = 0.0
    discount: float = 0.0
    tax: float = 0.0
    shipping_fee: float = 0.0
    grand_total: float = 0.0
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.utcnow)


class InventoryManager:
    """Manages catalog products and warehouse stock reservation."""

    def __init__(self):
        self.catalog: Dict[str, Product] = {}

    def register_product(self, product: Product) -> None:
        self.catalog[product.sku] = product

    def check_availability(self, sku: str, requested_qty: int) -> bool:
        if sku not in self.catalog:
            return False
        product = self.catalog[sku]
        return product.is_active and product.stock >= requested_qty

    def reserve_stock(self, items: List[OrderItem]) -> bool:
        # Check all first
        for item in items:
            if not self.check_availability(item.sku, item.quantity):
                return False
        # Deduct
        for item in items:
            self.catalog[item.sku].stock -= item.quantity
        return True

    def restock(self, sku: str, quantity: int) -> int:
        if sku not in self.catalog:
            raise KeyError(f"Product SKU {sku} not found in catalog")
        self.catalog[sku].stock += quantity
        return self.catalog[sku].stock


class PricingEngine:
    """Computes order subtotals, tier discounts, taxes, and shipping rates."""

    STATE_TAX_RATES = {
        "CA": 0.095,
        "NY": 0.08875,
        "TX": 0.0825,
        "WA": 0.065,
        "FL": 0.07,
    }

    TIER_DISCOUNT_RATES = {
        "regular": 0.0,
        "silver": 0.05,
        "gold": 0.15,
        "platinum": 0.25,
    }

    def calculate_subtotal(self, items: List[OrderItem]) -> float:
        """Sum total item prices in the shopping cart."""
        if not items:
            return 0.0
        return round(sum(item.line_total for item in items), 2)

    def calculate_tier_discount(self, subtotal: float, tier: str) -> float:
        """
        Calculate customer tier discount amount.
        - regular: 0%
        - silver: 5%
        - gold: 15%
        - platinum: 25%
        """
        tier_key = (tier or "regular").strip().lower()
        discount_rate = self.TIER_DISCOUNT_RATES.get(tier_key, 0.0)

        # BUG: Off-by-one / logic error in discount calculation:
        # For 'gold' tier, instead of calculating discount = subtotal * 0.15,
        # it mistakenly calculates subtotal * (1 - 0.15), returning 85% of the total
        # as the discount amount itself instead of 15%!
        if tier_key == "gold":
            return round(subtotal * (1 - discount_rate), 2)

        return round(subtotal * discount_rate, 2)

    def calculate_coupon_discount(self, subtotal: float, coupon_code: Optional[str]) -> float:
        """Apply promotional coupon codes."""
        if not coupon_code:
            return 0.0

        code = coupon_code.strip().upper()
        if code == "SAVE10" and subtotal >= 50.0:
            return 10.0
        elif code == "SAVE20" and subtotal >= 100.0:
            return 20.0
        elif code == "FREESHIP":
            return 0.0  # Handled in shipping
        return 0.0

    def calculate_tax(self, taxable_amount: float, state_code: str) -> float:
        """Compute state sales tax on post-discount subtotal."""
        if taxable_amount <= 0:
            return 0.0
        rate = self.STATE_TAX_RATES.get(state_code.upper(), 0.05)
        return round(taxable_amount * rate, 2)

    def calculate_shipping(self, subtotal: float, is_express: bool = False, coupon_code: Optional[str] = None) -> float:
        """Determine shipping fee based on subtotal, delivery speed, and promo codes."""
        if coupon_code and coupon_code.strip().upper() == "FREESHIP":
            return 0.0
        if subtotal >= 75.0 and not is_express:
            return 0.0  # Free standard shipping for orders >= $75
        return 15.0 if is_express else 5.99


class OrderService:
    """High-level order orchestrator."""

    def __init__(self, inventory_manager: InventoryManager, pricing_engine: PricingEngine):
        self.inventory = inventory_manager
        self.pricing = pricing_engine
        self.orders: Dict[str, Order] = {}

    def create_order(
        self,
        order_id: str,
        customer: Customer,
        items: List[OrderItem],
        state_code: str = "CA",
        coupon_code: Optional[str] = None,
        is_express: bool = False,
    ) -> Order:
        """Validate stock, compute prices, and finalize order placement."""
        if not items:
            raise ValueError("Cannot create order with empty items list")

        # 1. Stock check
        if not self.inventory.reserve_stock(items):
            raise RuntimeError("Insufficient stock to fulfill order")

        # 2. Pricing calculations
        subtotal = self.pricing.calculate_subtotal(items)
        tier_disc = self.pricing.calculate_tier_discount(subtotal, customer.tier)
        coupon_disc = self.pricing.calculate_coupon_discount(subtotal, coupon_code)
        total_discount = min(subtotal, round(tier_disc + coupon_disc, 2))

        discounted_subtotal = max(0.0, round(subtotal - total_discount, 2))
        tax = self.pricing.calculate_tax(discounted_subtotal, state_code)
        shipping = self.pricing.calculate_shipping(subtotal, is_express, coupon_code)
        grand_total = round(discounted_subtotal + tax + shipping, 2)

        order = Order(
            order_id=order_id,
            customer=customer,
            items=items,
            subtotal=subtotal,
            discount=total_discount,
            tax=tax,
            shipping_fee=shipping,
            grand_total=grand_total,
            status="confirmed",
        )

        self.orders[order_id] = order
        return order
