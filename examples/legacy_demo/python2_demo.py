# -*- coding: utf-8 -*-
# Python 2 demo for migration test

print 'migrating demo'
print 'count:', 3

def process(items):
    result = []
    for i in xrange(10):
        try:
            value = long(i) * 2
        except ValueError, e:
            print e
        result.append(value)
    return result

name = raw_input('your name: ')
text = u'你好'
if isinstance(text, basestring):
    text = unicode(text)
print 'done'
