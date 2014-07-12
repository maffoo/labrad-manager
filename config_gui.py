#!/usr/bin/python

from PyQt4 import QtCore, QtGui, uic
import os
import socket
import twisted.names.client as nameclient

class ManagerConfigDialog(QtGui.QDialog):
    def __init__(self, cfg):
        super(ManagerConfigDialog, self).__init__()
        uic.loadUi('manager_config.ui', self)
        self.cfg = cfg
        self.password.setText(cfg.password)
        self.name.setText(cfg.name)
        self.port.setText(str(cfg.port))
        self.registryPath.setText(cfg.registry)
        self.dirSelect.clicked.connect(self.do_dirSelect)
        self.autorun.setCheckState(2 if cfg.autorun else 0)

    def accept(self):
        self.cfg.password = str(self.password.text())
        self.cfg.name = str(self.name.text())
        self.cfg.port = int(self.port.text())
        self.cfg.autorun = bool(self.autorun.checkState())
        self.cfg.registry = str(self.registryPath.text())
        self.cfg.save()
        QtGui.QDialog.accept(self)

    def do_dirSelect(self):
        start_path = str(self.registryPath.text())
        if not os.exists(start_path):
            start_path = '.'
        dirname = str(QtGui.QFileDialog.getExistingDirectory(self, "Select Directory", directory=start_path))
        if dirname:
            self.registryPath.setText(dirname)


class ManagerBlacklistDialog(QtGui.QDialog):
    def __init__(self, blacklist):
        super(ManagerBlacklistDialog, self).__init__()
        uic.loadUi('manager_blacklist.ui', self)

        self.blacklist = blacklist
        #self.addr_list.cellDoubleClicked.connect(self.select_ip)
        self.actionAllow.clicked.connect(self.allow_ip)
        self.actionDeny.clicked.connect(self.deny_ip)
        self.insert.clicked.connect(self.insert_ip)
        self.remove.clicked.connect(self.remove_ip)
        self.addr_list.setColumnWidth(1, 120)
        self.addr_list.setColumnWidth(0, 50)

        for idx, (IP, netsize, hostname, allow) in enumerate(self.blacklist.items):
            self.addr_list.insertRow(idx)
            self.addr_list.setItem(idx, 0, QtGui.QTableWidgetItem(str(allow)))
            self.addr_list.setItem(idx, 1, QtGui.QTableWidgetItem("%s/%s" % (IP, netsize) ))
            if netsize > 32:
                self.addr_list.setItem(idx, 2, QtGui.QTableWidgetItem("<Network>"))
            elif hostname:
                self.addr_list.setItem(idx, 2, QtGui.QTableWidgetItem(hostname))
            else:
                self.addr_list.setItem(idx, 2, QtGui.QTableWidgetItem("<resolving>"))
                record_name = ".".join(IP.split(".")[::-1]) + ".in-addr.arpa"
                print "looking up IP address %s" % (record_name,)
                d = nameclient.lookupPointer(record_name)
                d.addCallbacks(callback = self.update_name, 
                               errback = self.name_error, 
                               callbackArgs = (idx,), 
                               errbackArgs = (idx,))

    def select_ip(self, row, col):
        selected_IP = self.addr_list.item(row, 1).text()
        self.activeHost.setText(selected_IP)

    def allow_ip(self):
        idx = self.addr_list.currentRow()
        if idx >= 0:
            self.addr_list.setItem(idx, 0, QtGui.QTableWidgetItem("True"))

    def deny_ip(self):
        idx = self.addr_list.currentRow()
        if idx >= 0:
            self.addr_list.setItem(idx, 0, QtGui.QTableWidgetItem("False"))

    def remove_ip(self):
        idx = self.addr_list.currentRow()
        if idx >= 0:
            self.addr_list.removeRow(idx)

    def insert_ip(self):
        addr = str(self.activeHost.text())
        self.activeHost.setText('')
        self.add_ip(addr)


    def add_hostname(self, hostname):
        d = nameclient.getHostByName(hostname)
        d.addCallback(self.add_ip)

    def add_ip(self, new_addr):
        print "adding host to list: %s" % (new_addr,)
        self.activeHost.setText('')
        if not new_addr:
            return
        if new_addr[0] not in "1234567890":
            self.add_hostname(new_addr)
            return
        new_addr, _, new_netsize = new_addr.partition('/')
        try:
            socket.inet_aton(new_addr)
        except Exception as e:
            print "Invalid IP"
            return
        new_netsize = int(new_netsize) if new_netsize else 32
        for idx in range(self.addr_list.rowCount()):
            old_addr = str(self.addr_list.item(idx, 1).text())
            old_addr, _, old_netsize = old_addr.partition('/')
            old_netsize = 32 if not old_netsize else int(old_netsize)
            if old_addr == new_addr and old_netsize == new_netsize:
                return
        idx = idx+1
        self.addr_list.insertRow(idx)
        self.addr_list.setItem(idx, 0, QtGui.QTableWidgetItem("False"))
        self.addr_list.setItem(idx, 1, QtGui.QTableWidgetItem("%s/%s" % (new_addr, new_netsize) ))
        if new_netsize < 32:
            self.addr_list.setItem(idx, 2, QtGui.QTableWidgetItem("<network>"))
        else:
            self.addr_list.setItem(idx, 2, QtGui.QTableWidgetItem("<resolving>"))
            record_name = ".".join(new_addr.split(".")[::-1]) + ".in-addr.arpa"
            print "looking up IP address %s" % (record_name,)
            d = nameclient.lookupPointer(record_name)
            d.addCallbacks(callback = self.update_name, 
                           errback = self.name_error, 
                           callbackArgs = (idx,), 
                           errbackArgs = (idx,))
        


    def update_name(self, records, idx):
        answers, authority, additional = records
        hostname = answers[0].payload.name
        print "Found hostname: %s of type %s" % (hostname,type(hostname))
        self.addr_list.setItem(idx, 2, QtGui.QTableWidgetItem(str(hostname)))
    def name_error(self, err, idx):
        self.addr_list.setItem(idx, 2, QtGui.QTableWidgetItem(" "))

        print "Unable to resolve record for idx %d" % (idx,)
        print "error: ", err
                               
    def accept(self):
        bl = []
        for idx in range(self.addr_list.rowCount()):
            allow = str(self.addr_list.item(idx, 0).text())
            allow = allow.lower() == "true"
            addr = str(self.addr_list.item(idx, 1).text())
            addr, _, netsize = addr.partition('/')
            netsize = 32 if not netsize else int(netsize)
            hostname = str(self.addr_list.item(idx, 2).text())
            bl.append((addr, netsize, hostname, allow))
        bl.sort(key=lambda x: x[1], reverse=True)
        self.blacklist.items = bl
        self.blacklist.save()
        QtGui.QDialog.accept(self)
