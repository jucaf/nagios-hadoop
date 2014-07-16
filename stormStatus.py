#!/usr/bin/env python
# vim: ts=4:sw=4:et:sts=4:ai:tw=80
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.
#
# AUTHOR: Juan Carlos Fernandez <jcfernandez@redoop.org>

from thrift import Thrift
from thrift.transport import TSocket
from thrift.transport import TTransport
from thrift.protocol import TBinaryProtocol

from storm import Nimbus
from storm.ttypes import *
from storm.constants import *


class StormStatus:
    def __init__(self,args):
	self.nimbus_connected = False
        self.nimbus_serv=args.nimbus_serv
        self.nimbus_port=args.nimbus_port
        self.topology=args.topology
        self.topologies=dict()
        self.get_topologies()
        if self.topology is not None:
            self.topologies_to_check=[self.topology]
        else:
            self.topologies_to_check=self.topologies.keys()
        for topology in self.topologies_to_check:
            self.get_topology_status(topology)

    def get_topologies(self):
        try:
            socket      = TSocket.TSocket(self.nimbus_serv,self.nimbus_port)
            transport   = TTransport.TFramedTransport(socket)
            protocol    = TBinaryProtocol.TBinaryProtocol(transport)
            client      = Nimbus.Client(protocol)

            transport.open()

            summary = client.getClusterInfo()
            
            transport.close()
            for topology in summary.topologies:
                self.topologies[str(topology.name)]={'id':topology.id,'components':{},'connected':False}
	    self.nimbus_connected = True

        except Thrift.TException, tx:
            print "%s" % (tx.message)

    def get_topology_status(self,topology):
        try:
            socket      = TSocket.TSocket(self.nimbus_serv,self.nimbus_port)
            transport   = TTransport.TFramedTransport(socket)
            protocol    = TBinaryProtocol.TBinaryProtocol(transport)
            client      = Nimbus.Client(protocol)

            transport.open()
            executors=client.getTopologyInfo(self.topologies[topology]['id']).executors
            for executor in executors:
                component=executor.component_id
                self.topologies[topology]['components'].setdefault(component, {'bolts':[], 'spouts':[]})
                task_start=executor.executor_info.task_start
                task_end=executor.executor_info.task_end
                spout_stats=executor.stats.specific.spout
                bolt_stats=executor.stats.specific.bolt
                if bolt_stats:
                    self.topologies[topology]['components'][component]['bolts'].append({ 
                        'id':str(task_start) + '-' + str(task_end),
                        'stats' : self.boltToDict(bolt_stats)})
	    self.topologies[topology]['connected'] = True
        except Thrift.TException, tx:
            print "%s" % (tx.message)

    def boltToDict(self,bolt_stats):
        out={'process_ms_avg':{},'executed':{},'execute_ms_avg':{},'acked':{},'failed':{},'load':{}}
        for period in [':all-time','86400','10800','600']:
            out['process_ms_avg'][period]=bolt_stats.process_ms_avg[period].values()[0] if bolt_stats.process_ms_avg[period] else 0
            out['executed'][period]=bolt_stats.executed[period].values()[0] if bolt_stats.executed[period] else 0
            out['execute_ms_avg'][period]=bolt_stats.execute_ms_avg[period].values()[0] if bolt_stats.execute_ms_avg[period] else 0
            out['failed'][period]=bolt_stats.failed[period].values()[0] if bolt_stats.failed[period] else 0
            out['acked'][period]=bolt_stats.acked[period].values()[0] if bolt_stats.acked[period] else 0
            out['load'][period]=out['process_ms_avg'][period]*out['executed'][period]/(int(period)*1000) if period != ":all-time" else 0
        return out
