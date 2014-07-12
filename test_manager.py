#!/usr/bin/python

import numpy as np
import os

#import labrad.fasttypes as types
import labrad.types as types
import time
import cProfile
profile=False
data1 = (1, [(" "*1500, "0"*15, "1"*15, 1500)]*1000)
data2 = (1, (np.arange(8192, dtype=np.int32), ) * 8)
data3 = (1, (np.arange(8192, dtype=np.uint32), ) * 8)
data4 = (1, (np.arange(8192) * 1.0, ) * 8)

data = [data1, data2, data3, data4]

str_be = []
for d in data:
    ot = types.getType(d)
    s, tt = types.flatten(d, ot, endianness='>')
    str_be.append((s,tt))

def performance_test():
    for j in range(20):
        unflattened = []
        for s in str_be:
            unflattened.append(types.unflatten(*s, endianness='>'))

        str_le = []
        for ufl in unflattened:
            str_le.append(types.flatten(ufl, endianness='<'))

def test_correctness(endianness='>'):
    '''
    Convert each data element to a string, then unflatten/flatten it and see if we
    have the same string.  This is easier than trying to compare arbitrary data structures
    to see if they have been preserved.
    '''

    slist = []
    for d in data:
        ot = types.getType(d)
        s, tt = types.flatten(d, ot, endianness)
        slist.append((s,tt))
    for idx, s in enumerate(slist):
        new_data= types.unflatten(*s, endianness=endianness)
        new_string = types.flatten(new_data, types.getType(new_data), endianness)
        if new_string != s:
            print "Data mismatch on index %d with byte order %s" % (idx, endianness)

if __name__ == '__main__':
    test_correctness('>')
    test_correctness('<')
