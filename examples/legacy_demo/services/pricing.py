def apply_tier_discount(order):
    total = order.subtotal()
    if total >= 500:
        discount = 0.2
    elif total >= 200:
        discount = 0.1
    else:
        discount = 0.0
    return int(total * (1 - discount))


def bulk_bonus(order):
    bonus = 0
    for i in xrange(len(order.items)):
        bonus += order.items[i][1]
    return bonus // 10
