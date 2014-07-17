#!/usr/bin/python

import sys
import os
#sys.path.insert(0, '/home/hobbes/src/pylabrad-0.93.1/')
#if __name__ == "__main__":
#    if os.name == "posix":
#        sys.path.insert(0, os.path.join(os.environ['HOME'], 'src/pylabrad-0.93.#1/'))
#    elif os.name == "nt":
#        base_path = "U://"

import twisted.internet.reactor as reactor
import twisted.internet.protocol as protocol
from labrad.protocol import LabradProtocol
from labrad.server import LabradServer, setting, ServerProtocol
from labrad.stream import packetStream, flattenPacket
import labrad
import traceback
import twisted.python.randbytes
import hashlib
import base64
import collections
from manager_server import ManagerServer, InMemoryProtocol
#from twisted.cred import portal, checkers
#from twisted.conch import manhole, manhole_ssh
import registry
import manager_config
import blacklist

class EndianAdaptingProtocol(LabradProtocol):
    '''
    This is only for use by the labrad manager.  The labrad protocol
    allows each client to choose their endianness, and the labrad
    manager detects that implicitly from the first packet and does
    conversions as necessary.  

    It would be better (and should be implemented in future versions)
    that all communication is done in big-endian aka network byte
    order.  If done properly it doesn't add much overhead to
    flattening and unflattening, and we save effort of doing multiple
    conversions in the manager.
    '''
    def __init__(self):
        LabradProtocol.__init__(self)
        self.endian=None
        self.packetStream = None
        self.data_buffer = '' # Used until we detect endianness

    def dataReceived(self, data):
        if not self.endian:
            self.data_buffer += data
            if len(data) < 20:
                return
            if ord(data[12]):
                self.endian = '<'
            else:
                self.endian = '>'
            print "Found byte order: ", self.endian
            self.packetStream = packetStream(self.packetReceived, endianness=self.endian)
            self.packetStream.next()
            self.packetStream.send(self.data_buffer)
            del self.data_buffer
        else:
            self.packetStream.send(data)
    def sendPacket(self, target, context, request, records):
        """Send a raw packet to the specified target."""
        # FIXME: if transport.write() fails asynchronously, we need an errback
        # to generate an error response for the source.
        raw = flattenPacket(target, context, request, records, endianness=self.endian)
        self.transport.write(raw)


# Protocol: 1 per connection, has a reference to the factory
class LabradManager(EndianAdaptingProtocol):
    def __init__(self):
        self.ID = 0 # real ID set when authenticated
        self.state = 0 # Starting state
        EndianAdaptingProtocol.__init__(self)
        #super(LabradManager, self).__init__()

    def connectionMade(self):
        '''
        Handle a new connection.  We register with the manager which 
        is responsible for checking the blacklist.
        '''
        try:
            self.factory.connectionMade(self)
        except Exception as e:
            print "connection made failed, dropping connection"
            self.transport.loseConnection()

        EndianAdaptingProtocol.connectionMade(self)

        try:
            self.pw_challenge = base64.b64encode(twisted.python.randbytes.secureRandom(10))
        except twisted.python.randbytes.SecureRandomNotAvailable:
            self.transport.abortConnection()

    def connectionLost(self, reason):
        EndianAdaptingProtocol.connectionLost(self, reason)
        if self.ID:
            self.factory.unregister_connection(self.ID)
            self.ID=0

    def packetReceived_flat(self, dest, context, request, data):
        if not self.ID:
            requests = stream.unflattenRecords(data)
            self.packetRecieved(dest, context, request, records)
        else:
            self.factory.handlePacket_flat(self.ID, dest, context, request, data)

    # In the manager, packets always come in with the destination instead of 
    # the source, and leave with the source.  This is the opposite of what
    # happens in clients, so the arguments names are reversed from the
    # base class.
    def packetReceived(self, dest, context, request, records):
        '''
        Packet received from a client.  If the connection does not yet
        have an ID, pass to the login code.  Otherwise pass to the
        factory which does communication with the manager server or
        other clients.
        '''
        if not self.ID:
            self.handleLogon(dest, context, request, records)
            return # discard messages before we are connected
        try:
            self.factory.handlePacket(self.ID, dest, context, request, records)
        except Exception as e:
            # If the manager can't figure out how to dispach the
            # packet, we need to generate an error response here or
            # the client will wait forever for a response.  If
            # handlePacket succeeds, it is required that one way or
            # another an error or a response is returned to the
            # client.  In particular. this means that if the eventual
            # call to write() fails asynchronously, we need to make
            # sure an errback generates an error response!  This is
            # not currently done!  FIXME

            print "handlePacket error, generating error response"
            response = []
            for record in records:
                setting = record[0]
                data = record[1]
                # record[2] is the type tag is present.
                response.append((setting, labrad.types.Error(e)))
                # Not sure if the source should be 1 (manager) or the failed destination
                self.sendPacket(1, context, -request, response)
            raise

    def sendPacket(self, dest, context, request, records):
        '''
        Sends a packet from the manager to the client.
        '''
        #print "Sending packet %s to dest: %s %s records: %s" % (request, dest, context, records)
        EndianAdaptingProtocol.sendPacket(self, dest, context, request, records)

    def handleLogon(self, dest, context, request, records):
        '''
        It takes 3 packets to set up a connection.  The first one is used to identify the endianness,
        the second for authentication, and the final tells whether the connection is for a client
        or server and assigns the connection ID.
        '''
        # Packet 1: origin client, target 1, context any, request ID: positive, no records
        # Response: from source ID 1, same context, -request ID, single response settnig 0: (s) pw challenge
        if self.state==0:   # Connect
            if dest==1 and not len(records):
                self.state = 1
                self.sendPacket(dest, context, -request, [(0, self.pw_challenge, 's')]) # send password challenge
            else:
                self.transport.abortConnection()
        # Packet 2: origin client: target 1, context any, request ID: positive, setting 0 MD5(pw_challenge + pw)
        # Response: from setting 0: (s) welcome message or error
        elif self.state==1: # Authentication
            if dest==1 and len(records)==1:
                setting, data = records[0]
                if setting != 0:
                    self.transport.abortConnection()
                    return
                pw_response = hashlib.md5(self.pw_challenge + self.factory.password).digest()
                if data == pw_response:
                    self.state=2
                    self.sendPacket(dest, context, -request, [(0, 'Welcome to LabRAD')])
                else:
                    self.sendPacket(dest, context, -request, [(0, labrad.types.Error('Password Invalid'))])
                    self.transport.loseConnection()
            else:
                self.transport.abortConnection()
        # Packet 3: target 1, context any, request ID any, setting 0 (ws) or (wsss) for client/server
        # containing protocol version, client/server name, description, remarks.
        # Response: from setting 0: (w) connection ID or error.
        elif self.state==2: # Client/Server Selection
            if dest==1 and len(records) == 1:
                setting, data = records[0]
                if setting != 0:
                    self.transport.abortConnection()
                    return
                try:
                    proto_version = data[0]
                    if proto_version != 1:
                        self.sendPacket(dest, context, -request, 
                                        [(0, labrad.types.Error('Invalid Protocol Version'))])
                        self.transport.loseConnection()
                        return
                    if len(data) == 4:
                        proto_version, server_name, desc, remarks = data
                        ID = self.factory.register_server(self, server_name, desc, remarks)
                        print "allocated ID %d" % ID
                        if ID>0:
                            self.ID = ID
                            self.state = 3
                            self.sendPacket(dest, context, -request, [(0,long(ID))])
                        else:
                            self.sendPacket(dest, context, -request, 
                                            [(0, labrad.types.Error('Unable to allocate ID for server'))])
                            self.transport.loseConnection()
                    if len(data) == 2:
                        proto_version, client_name = data
                        ID = self.factory.register_client(self, client_name)
                        print "allocated ID %d" % ID
                        self.ID = ID
                        self.sendPacket(dest, context, -request, [(0, long(ID))])
                except Exception as e:
                    raise
                    self.sendPacket(dest, context, -request, [(0,e)])

def runLocalServer(cfg, srv):
    '''
    Connect a server to the manager over the loopback connection.
    '''
    srv.password = cfg.password
    reactor.connectTCP('localhost', cfg.port, srv)
    
# ServerFactory 1 per server.  Constructs Protocol objects for every connection
class LabradManagerFactory(protocol.ServerFactory):
    '''
    The LabradManagerFactory actually handles most of the business of the labrad manager
    since it knows about all the client connections.  This takes care of receiving messages
    and dispatching them to the correct client protocol object.  Requests targeted at the
    manager are intercepted and sent to a special in-memory server.
    '''
    protocol = LabradManager
    def __init__(self, cfg, blacklist):
        # 
        # connections = {ID: protocol}
        # 
        self.connections = {} # (ID -> (protocol object, name) )
        self.password = cfg.password
        self.manager = ManagerServer(cfg.name, cfg.uuid)
        self.blacklist = blacklist
        manager_protocol = self.manager.protocol(self, 1)
        manager_protocol.factory = self.manager
        try:
            self.manager._connectionMade(manager_protocol)
        except Exception as e:
            print e
            raise
        self.connections[1] = manager_protocol
        
    def handlePacket(self, source, dest, context, request, records):
        # (0,0) seems to be a special context when talking to the manager.  In particular,
        # context expiration notices have to come from (0,0).  Since the manager doesn't keep context
        # information, 
        if context[0] == 0 and context[1] != 0 and not (source==1 or dest==1):
            context = (source, context[1])
        self.manager.update_packet_counts(source, dest)
        self.manager.register_context(source if request >= 0 else dest, context)

#        if dest in self.connections:
        target = self.connections[dest]
#        print "tgt: %s, src: %s, ctx: %s, req: %s, rec: %s" % (target.ID, source, context, request, records)
        if isinstance(target, InMemoryProtocol):
            # the only InMemoryProtocol is the Manager itself (the
            # registry is in the same process but connects via TCP to
            # the loopback address.  The key difference for an
            # InMemoryProtocol is that it doesn't have an underlying
            # transport and the messages are not flattened and
            # unflattened.
            target.requestReceived(source, context, request, records)
        else:
            # This compares the record data types to those registered
            # for each server setting ID, and attempts to coerce them.
            # This is slow, and needs to be optimized, possibly with a
            # C implementation.  Better yet, we would get the records
            # unflattened.
            try:
                records = self.manager.update_types(source, dest, request, records)
            except Exception as e:
                print "failed to update types"
                traceback.print_exc()
                raise
            target.sendPacket(source, context, request, records)

    def stopFactory(self):
        print "factory stopping"
        protocol.ServerFactory.stopFactory(self)
        for k,p in self.connections.items():
            if k==1:
                continue
            p.transport.loseConnection()
            print "Dropping connection ID %s" % k
        self.connections[1].connectionLost(protocol.connectionDone)
        #del self.manager

    def startFactory(self):
        print "starting factory"
        protocol.ServerFactory.startFactory(self)
    def register_server(self, protocol, server_name, desc, remarks):
        '''
        Called when a new server connection happens.  Here we just need to know
        the ID->Protocol object mapping, but we need to also notify the in-memory
        manager server so that it can manage the list of settings.
        '''
        ID = self.manager.register_server(server_name, desc, remarks)
        if ID:
            self.connections[ID] = protocol
        return ID

    def register_client(self, protocol, client_name):
        '''
        Called when a new client connection happens.  Here we just need to know
        the ID->Protocol object mapping, but we need to also notify the in-memory
        manager server.
        '''
        ID = self.manager.register_client(client_name)
        if ID:
            self.connections[ID] = protocol
        return ID

    def unregister_connection(self, ID):
        print "unregistering connection %s" % ID
        self.manager.unregister_connection(ID)
        del self.connections[ID]

    def connectionMade(self, prot):
        '''
        Checks the blacklist.
        '''
        addr = prot.transport.getPeer()
        if not self.blacklist.check_ip(addr.host):
            raise RuntimeError("IP blacklisted")
        # check whitelest addr.host, addr.port


def getManholeFactory(namespace, **passwords):
    realm = manhole_ssh.TerminalRealm()
    def getManhole(_): return manhole.Manhole(namespace)
    realm.chainedProtocolFactory.protocolFactory = getManhole
    p = portal.Portal(realm)
    p.registerChecker(
        checkers.InMemoryUsernamePasswordDatabaseDontUse(**passwords))
    f = manhole_ssh.ConchFactory(p)
    return f

def main():
    # manager_config and blacklist import Qt.  Separate them out
    cfg = manager_config.ManagerConfig()
    bl = blacklist.Blacklist()

    factory = LabradManagerFactory(cfg, bl)
    listener = reactor.listenTCP(cfg.port, factory)
    reg = registry.Registry(cfg.registry)
    reg.password = cfg.password
    # Registry is in-process, but connects over a normal socket.
    reactor.connectTCP('localhost', cfg.port, reg)
    reactor.run()
    
if __name__ == '__main__':
    main()

