class Order(object):
    def __init__(self):
        self.items = []

    def add_item(self, product, count):
        self.items.append((product, count))

    def subtotal(self):
        total = 0
        for product, count in self.items:
            total += product.price * count
        return total
