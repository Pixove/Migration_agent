def print_order_report(order, total, bonus):
    title = u'订单明细'
    print '=== ' + title + ' ==='
    for product, count in order.items:
        print product.name, 'x', count, '=', product.price * count
    print '--- 合计 ---'
    print '总计:', total
    print '积分:', bonus
