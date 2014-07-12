#!/usr/bin/python

import ConfigParser
import uuid
import re 
import os

def inifile_property(name, itemtype=''):
    def fget(self):
        func = getattr(self.sfp, 'get%s' % itemtype)
        return func('LabRAD', name)
    def fset(self, val):
        return self.sfp.set('LabRAD', name, str(val))
    return property(fget, fset)

class ManagerConfig(object):

    def __init__(self, inifile="LabRAD.ini"):
        self.inifile = inifile
        self.sfp = ConfigParser.SafeConfigParser()
        self.sfp.add_section('LabRAD')
        self.sfp.add_section('Whitelist')
        self.port = 7682
        self.password = ''
        self.autorun = False
        self.name = ''
        self.uuid = uuid.uuid1()
        self.registry = './Registry'
        self.sfp.read(inifile)

    port = inifile_property('Port', 'int')
    autorun = inifile_property('Auto-Run', 'boolean')
    password = inifile_property('Password', '')
    name = inifile_property('Name', '')
    uuid = inifile_property('UUID', '')
    registry = inifile_property('Registry', '')

    def load_whitelist(self):
        wl = []
        for (net, allow) in self.sfp.items('Whitelist'):
            mo = re.match("([\d.+]*)(?:/(\d+))?", net)
            address = mo.group(1)
            mask = int(mo.group(2) or 32)
            wl.append((address, mask, allow))
        self.whitelist =  wl

    def save(self):
        tempfile = self.inifile + ".tmp"
        with open(tempfile, 'w') as f:
            self.sfp.write(f)
            f.flush()
            os.fsync(f.fileno())
        if os.name != 'posix': # Windows doesn't get atomic renames.  Sad.
            os.remove(self.inifile)
        os.rename(tempfile, self.inifile)
        
