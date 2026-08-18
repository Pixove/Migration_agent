# -*- coding: utf-8 -*-
import sys

from models.order import Order
from services.pricing import apply_tier_discount, bulk_bonus
from services.report import print_order_report
from utils.storage import load_products

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass


def main():
    products = load_products('data/products.txt')
    order = Order()
    for product in products:
        order.add_item(product, 1)

    total = apply_tier_discount(order)
    bonus = bulk_bonus(order)
    print_order_report(order, total, bonus)
    return 0


if __name__ == '__main__':
    main()
