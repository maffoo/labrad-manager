#!/usr/bin/python
import sys
import os
#if __name__ == "__main__":
#    if os.name == "posix":
#        sys.path.insert(0, os.path.join(os.environ['HOME'], 'src/pylabrad-0.93.#1/'))
##    elif os.name == "nt":
#        base_path = "U://"

from PyQt4 import QtCore, QtGui, uic
import qtreactor.qt4reactor as qt4reactor
app = QtGui.QApplication(sys.argv)
qt4reactor.install()
import pymanager
from twisted.internet.task import LoopingCall
import manager_config
import blacklist
import config_gui
import registry

class ManagerMainWindow(QtGui.QMainWindow):
    def __init__(self, reactor):
        super(ManagerMainWindow, self).__init__()
        uic.loadUi('manager_gui.ui', self)

        self.connection_list.setColumnWidth(1, 300)
        self.connection_list.sortByColumn(0, QtCore.Qt.AscendingOrder)
        self.reactor = reactor

        self.cfg = manager_config.ManagerConfig()
        self.blacklist = blacklist.Blacklist()

        self.actionRun.toggled.connect(self.on_run)
        self.actionDrop.triggered.connect(self.on_drop)
        self.actionConfig.triggered.connect(self.on_config)
        self.actionWhitelist.triggered.connect(self.on_whitelist)

        if self.cfg.autorun:
            print "Autorun enabled"
            self.actionRun.setChecked(True)
    
        #self.actionConfig.triggered.connect(self.on_config)
        #self.actionWhitelist.triggered.connect(self.on_whitelist)
        #self.actionSave.triggered.connect(self.on_save)

    def on_run(self, state):
        if state:
            print "starting manager"
            self.factory = pymanager.LabradManagerFactory(self.cfg, self.blacklist)
            self.listener = self.reactor.listenTCP(self.cfg.port, self.factory)
            print "starting registry"
            reg = registry.Registry(self.cfg.registry)
            reg.password = self.cfg.password
            self.reactor.connectTCP('localhost', self.cfg.port, reg)
            self.cb = LoopingCall(self.update_connections)
            self.cb.start(interval=0.25, now=True)
        else:
            print "stopping manager"
            self.cb.stop()
            self.listener.stopListening()
            del self.factory
            while self.connection_list.rowCount():
                self.connection_list.removeRow(0)
        print "self.run_action: %s" %(state)

    def update_connections(self):
        connections = dict(self.factory.manager.server_list.items() + self.factory.manager.client_list.items())
        self.connection_list.setSortingEnabled(False)
        existing_connections = set()
        for idx in reversed(range(self.connection_list.rowCount())):
            ID = int(self.connection_list.item(idx, 0).text())
            existing_connections.add(ID)
            try:
                self.connection_list.setItem(idx, 2, QtGui.QTableWidgetItem(str(connections[ID].sent_pkts)))
                self.connection_list.setItem(idx, 3, QtGui.QTableWidgetItem(str(connections[ID].recv_pkts)))
            except KeyError:
                self.connection_list.removeRow(idx)
        
        for k, cxn in connections.items():
            if k not in existing_connections:
                self.connection_list.insertRow(0)
                self.connection_list.setItem(0, 0, QtGui.QTableWidgetItem(str(cxn.ID)))
                self.connection_list.setItem(0, 1, QtGui.QTableWidgetItem(cxn.name))
                self.connection_list.setItem(0, 2, QtGui.QTableWidgetItem(str(cxn.sent_pkts)))
                self.connection_list.setItem(0, 3, QtGui.QTableWidgetItem(str(cxn.recv_pkts)))
        self.connection_list.setSortingEnabled(True)
                
        
    def showEvent(self, ev):
        print "Show event"

    def closeEvent(self, ev):
        print "close event, shutting down reactor"
        self.reactor.stop()

    def on_drop(self):
        print "Dropping connection"
        ID = int(self.connection_list.item(self.connection_list.currentRow(), 0).text())
        if ID <= 1:
            return # Can't drop the manager
        self.factory.connections[ID].transport.loseConnection()
        
    def on_config(self):
        dlg = config_gui.ManagerConfigDialog(self.cfg)
        rv = dlg.exec_()
        print "on config"
        print "return value: ", rv

    def on_whitelist(self):
        dlg = config_gui.ManagerBlacklistDialog(self.blacklist)
        rv = dlg.exec_()
        print "on whitelist"
        print "return value: ", rv

    def on_save(self):
        print "on save"
        

def main():
    #app = QtGui.QApplication(sys.argv)
    from twisted.internet import reactor
    w = ManagerMainWindow(reactor)
    w.show()
    rv = reactor.run()
    sys.exit(rv)

if __name__ == "__main__":
    main()
