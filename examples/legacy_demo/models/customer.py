# -*- coding: utf-8 -*-


class Customer(object):
    def __init__(self, name, level):
        if isinstance(name, basestring):
            name = unicode(name)
        self.name = name
        self.level = level

    def is_member(self):
        return self.level == 'V'
