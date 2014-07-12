#!/usr/bin/python
#
# Provides a module for maintaining an IP white/black list and checking if
# new connections are allowed.


import socket
import struct
import re
import csv

class Blacklist(object):
    def __init__(self, filename='LRWhitelist.csv'):
        # load from config file
        self.filename = filename
        self.items = []

        try:
            with open(self.filename, 'rb') as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) != 4:
                        raise RuntimeError()
                    self.items.append( (row[0], int(row[1]), row[2], row[3].lower()=='true') )
        except IOError: # File not found
            items = [('127.0.0.1', 32, 'localhost', True)]
            pass
        # item format: [(IP, netsize, hostname, allow), ...]

    def save(self):
        tempfile = self.filename + ".tmp"
#        with open(self.filename, 'wb') as f:
        with open(tempfile, 'wb') as f:
            writer = csv.writer(f)
            for row in self.items:
                writer.writerow(row)
            f.flush()
            os.fsync(f.fileno())
        if os.name != 'posix':
            os.remove(self.filename)
        os.rename(tempfile, self.filename)
    def check_ip(self, host):
        print "Checking host %s for allowed IP" % (host,)
        host_addr = struct.unpack('>I', socket.inet_aton(host))[0]
        for IP, netsize, hostname, allow in self.items:
            addr = struct.unpack('>I', socket.inet_aton(IP))[0]
            if (addr >> (32-netsize)) == (host_addr >> (32-netsize)):
                print "Allowing connection from host %s? %s" % (host,allow)
                return allow
        # Insert single address at the beginning so that most specific
        # items are checked first. 
        print "Host %s unknown, adding to blacklist and disallowing" % (host,)
        self.items.insert(0, (host, 32, None, False) )
        return False
