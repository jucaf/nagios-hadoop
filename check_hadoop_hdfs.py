#!/usr/bin/env python
# vim: ts=4:sw=4:et:sts=4:ai:tw=80
from requests_kerberos import HTTPKerberosAuth
from utils import krb_wrapper,StringContext
import os
import argparse
import requests
import re
import subprocess
import nagiosplugin
import logging

html_auth = None

def parser():
    version="0.1"
    parser = argparse.ArgumentParser(description="Checks datanode")
    parser.add_argument('-p', '--principal', action='store', dest='principal')
    parser.add_argument('-s', '--secure',action='store_true')
    parser.add_argument('-k', '--keytab',action='store')
    parser.add_argument('--cache_file',action='store', default='/tmp/nagios.krb')
    parser.add_argument('-nn','--namenodes',action='store')
    parser.add_argument('--warning_used',action='store', type=float,default=70.00)
    parser.add_argument('--warning_blocks',action='store', type=int,default=250000)
    parser.add_argument('--warning_balanced',action='store',type=float,default=5.00)
    parser.add_argument('--warning_corrupt',action='store',type=int,default=0)
    parser.add_argument('--warning_missing',action='store',type=int,default=0)
    parser.add_argument('--warning_ureplicated',action='store',type=int,default=20)
    parser.add_argument('--critical_used',action='store', type=float,default=85)
    parser.add_argument('--critical_blocks',action='store', type=int,default=350000)
    parser.add_argument('--critical_balanced',action='store',type=float,default=10.00)
    parser.add_argument('--critical_corrupt',action='store',type=int,default=10)
    parser.add_argument('--critical_datanodes',action='store',type=int,default=3)
    parser.add_argument('--critical_missing',action='store',type=int,default=10)
    parser.add_argument('--critical_ureplicated',action='store',type=int,default=50)
    parser.add_argument('-v','--version', action='version', version='%(prog)s ' + version)
    args = parser.parse_args()
    if args.secure and (args.principal is None or args.keytab is None):
        parser.error("if secure cluster, both of --principal and --keytab required")
    return args

class Hdfs(nagiosplugin.Resource):
    totalTest=['DFS Used%']
    datanodesTest=['Total Blocks']

    """
    Return dict struture with the format:
    {NODE<<String>>:{FIELD<<String>>:VALUE}}
    where NODE could be Total or a datanode FQDN and FIELD:
        'Blocks with corrupt replicas'
        'Configured Capacity'
        'Decommission Status'
        'DFS Remaining'
        'DFS Used'
        'DFS Used%'
        'Hostname'
        'Last contact'
        'Missing blocks'
        'Non DFS Used'
        'Present Capacity'
        'Under replicated blocks'
    """
    def parser_hdfsreport(self):
        p = subprocess.Popen(['hdfs','dfsadmin','-report'],stdout=subprocess.PIPE) 
        output,err = p.communicate()
        hdfsreport = dict()
        if err is None:
            host = 'Total'
            hdfsreport[host]=dict()
            for line in output.splitlines():
                m = re.match('^(?P<FIELD>\w+(\s\w+)*%?)\s*:\s*(?P<VALUE>.*?)(\s*\((?P<HUMAN>.+)\))?$',line)
                if m:
                    if m.group('FIELD')=="Name":
                        host=m.group('HUMAN')
                        hdfsreport[host]=dict()
                        hdfsreport[host][m.group('FIELD')] = m.group('VALUE')
                    else:
                        hdfsreport[host][m.group('FIELD')] = m.group('VALUE')
                        if m.group('HUMAN'):
                            hdfsreport[host][m.group('FIELD')+'_human'] = m.group('HUMAN')
        else:
            return 2,"Critical: "+err
        return 0,hdfsreport

    """
    Return dict structure with the format
    {FIELD<<String>>:VALUE<<int>>}
    where FIELD could be:
       'Total Blocks'
       'Verified in last hour'
       'Verified in last day'
       'Verified in last week'
       'Verified in last four weeks'
       'Verified in SCAN_PERIOD'
       'Not yet verified'
       'Verified since restart'
       'Scans since restart'
       'Scan errors since restart'
       'Transient scan errors'
       'Current scan rate limit KBps'
       'Progress this period'
       'Time left in cur period'
    """
    def blockscanner(self,datanode,port):
        blockscanner=dict()
        output = requests.get("http://" + datanode + ':' + str(1006) + "/blockScannerReport", auth=self.html_auth)
        for line in output.content.splitlines():
            m = re.match('^(\w+(\s\w+)*)\s*:\s*(\d*)$',line)
            if m:
                blockscanner[m.group(1)] = int(m.group(3))
        return blockscanner

    def getBalance(self):
        max=0
        min=100
        for datanode in self.hdfsreport.keys():
            if datanode != 'Total':
                used=float(self.hdfsreport[datanode]['DFS Used%'].replace('%',''))
                if used>max:
                    max = used
                if used<min:
                    min = used
        return max-min

    def getNamenodesRol(self,namenodes):
        namenodes_rol=dict()
        for namenode in namenodes.split(','):
            instance = namenode.split('.')[0]
            p = subprocess.Popen(['hdfs','haadmin','-getServiceState',instance],stdout=subprocess.PIPE)
            output,err = p.communicate()
            if err is None:
                namenodes_rol[namenode]=output.rstrip()
            else:
                namenodes_rol[namenode]=err
        return namenodes_rol



    def __init__(self,html_auth,namenodes):
        self.html_auth = html_auth
        status,self.hdfsreport = self.parser_hdfsreport()
        for datanode in self.hdfsreport.keys():
            if datanode != 'Total':
                port = self.hdfsreport[datanode]['Name'].split(':')[1]
                self.hdfsreport[datanode]['blockscanner']=self.blockscanner(datanode,port)
        self.namenodes=self.getNamenodesRol(namenodes)
     
    def probe(self):
        yield nagiosplugin.Metric('Active NN',sum([1 for nn in self.namenodes if self.namenodes[nn]=='active']),min=0 ,context ="active nn")
        yield nagiosplugin.Metric('Standby NN',sum([1 for nn in self.namenodes if self.namenodes[nn]=='standby']),min=0 ,context ="standby nn")
        yield nagiosplugin.Metric('used%',float(self.hdfsreport['Total']['DFS Used%'].replace('%','')),min=0 ,context = "used")
        yield nagiosplugin.Metric('datanodes',int(self.hdfsreport['Total']['Datanodes available']),min=0 ,context = "datanodes")
        yield nagiosplugin.Metric('under_replication', int(self.hdfsreport['Total']['Under replicated blocks']), min = 0, context = "ureplicated")
        yield nagiosplugin.Metric('missing_blocks',int(self.hdfsreport['Total']['Missing blocks']),min=0 , context = "missing")
        yield nagiosplugin.Metric('corrupted_replicas',int(self.hdfsreport['Total']['Blocks with corrupt replicas']),min=0, context = "corrupt")
        yield nagiosplugin.Metric('balanced',self.getBalance(),min=0, context = "balanced")
        for datanode in self.hdfsreport.keys():
            if datanode != 'Total':
                yield nagiosplugin.Metric(datanode, int(self.hdfsreport[datanode]['blockscanner']['Total Blocks']), min = 0,context = "total_blocks")
        

class HdfsSummary(nagiosplugin.Summary):
    def ok(self,result):
        return 'Total DFS storage in use is %s%%' % (str(result['used%'].metric))

@nagiosplugin.guarded
def main():
    args = parser()
    if args.secure:
        html_auth=HTTPKerberosAuth()
        auth_token = krb_wrapper(args.principal,args.keytab,args.cache_file)
        os.environ['KRB5CCNAME'] = args.cache_file
    check = nagiosplugin.Check(Hdfs(html_auth,args.namenodes),
        StringContext('active nn',
            1,
            fmt_metric='{value} active namenodes'),
        StringContext('standby nn',
            len(args.namenodes.split(','))-1,
            fmt_metric='{value} standby namenodes'),
        nagiosplugin.ScalarContext('used',
            args.warning_used,
            args.critical_used,
            fmt_metric='{value}% storage in use'),
        nagiosplugin.ScalarContext('total_blocks',
            args.warning_blocks,
            args.critical_blocks,
            fmt_metric=' is using {value} blocks'),
        nagiosplugin.ScalarContext('ureplicated',
            args.warning_ureplicated,
            args.critical_ureplicated,
            fmt_metric='{value} under replicated blocks'),
        nagiosplugin.ScalarContext('missing',
            args.warning_missing,
            args.critical_missing,
            fmt_metric='{value} missing blocks'),
        nagiosplugin.ScalarContext('corrupt',
            args.warning_corrupt,
            args.critical_corrupt,
            fmt_metric='{value} corrupted blocks'),
        nagiosplugin.ScalarContext('balanced',
            args.warning_balanced,
            args.critical_balanced,
            fmt_metric='There are {value}% usage difference between datanodes'),
        StringContext('datanodes',
            args.critical_datanodes,
            fmt_metric='{value} living datanodes'), 
        HdfsSummary())
    check.main()
    if auth_token: auth_token.destroy() 

if __name__ == '__main__':
    main()