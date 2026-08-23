import codecs

from models.customer import Customer
from models.product import Product


def load_products(path):
    products = []
    try:
        with codecs.open(path, 'r', 'utf-8') as handle:
            for line in handle:
                parts = line.strip().split(',')
                products.append(Product(parts[0], parts[1], int(parts[2])))
    except IOError, e:
        print '读取文件失败:', e
    return products


def load_customers(path):
    customers = []
    try:
        with codecs.open(path, 'r', 'utf-8') as handle:
            for line in handle:
                parts = line.strip().split(',')
                customers.append(Customer(parts[0], parts[1]))
    except Exception, e:
        print '客户加载失败:', e
    return customers
