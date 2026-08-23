def print_order_report(order, customer, subtotal, total, bonus):
    title = u'订单明细'
    print '=== ' + title + ' ==='
    print '客户:', customer.name, '会员:', customer.level
    for product, count in order.items:
        print product.name, 'x', count, '=', product.price * count
    print '--- 金额 ---'
    print '小计:', subtotal
    print '会员价:', total
    print '积分:', bonus
