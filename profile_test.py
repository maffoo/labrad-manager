#!/usr/bin/python

import labrad.types

def main():
    n=1000000
    mac = "00:00:00:00:00:00"
    data = "{:{n}s}".format(" ", n=1500)
    pkt = (mac, mac, len(data), data)
    pkts = [pkt]*n
    

    x, t = labrad.types.flatten(pkts, ['*(ssis)'], '>')
    #t = str(t)
    #labrad.types.unflatten(x, t, '>')


if __name__ == "__main__":
    main()
