# -*- coding: utf-8 -*-


class Product(object):
    def __init__(self, name, price, quantity):
        if isinstance(name, basestring):
            name = unicode(name)
        self.name = name
        self.price = long(price) if isinstance(price, basestring) else price
        self.quantity = quantity

    def stock_value(self):
        return self.price * self.quantity
