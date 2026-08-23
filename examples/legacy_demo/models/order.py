class Order(object):
    def __init__(self):
        self.items = []

    def add_item(self, product, count):
        self.items.append((product, count))

    def subtotal(self):
        total = 0
        for i in xrange(len(self.items)):
            product, count = self.items[i]
            total += product.price * count
        return total
