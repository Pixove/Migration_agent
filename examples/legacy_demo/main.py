# -*- coding: utf-8 -*-
import sys

from models.order import Order
from services.pricing import apply_member_discount, apply_tier_discount, bulk_bonus
from services.report import print_order_report
from utils.storage import load_customers, load_products

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass


def main():
    products = load_products('data/products.txt')
    customers = load_customers('data/customers.txt')
    customer = customers[0]

    order = Order()
    for product in products:
        order.add_item(product, 1)

    subtotal = order.subtotal()
    tier_total = apply_tier_discount(subtotal)
    total = apply_member_discount(tier_total, customer)
    bonus = bulk_bonus(order)
    print_order_report(order, customer, subtotal, total, bonus)
    return 0


if __name__ == '__main__':
    main()
