import codecs

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
