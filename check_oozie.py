#!/usr/bin/env python
from requests_kerberos import HTTPKerberosAuth
from utils import krb_wrapper
import os
import argparse
import requests
import nagiosplugin
import ooziestatus

def parser():
    version="0.1"
    parser = argparse.ArgumentParser(description="Checks oozie")
    parser.add_argument('-p', '--principal', action='store', dest='principal')
    parser.add_argument('-s', '--secure',action='store_true')
    parser.add_argument('-k', '--keytab',action='store')
    parser.add_argument('--cache_file',action='store', default='/tmp/nagios.krb')
    parser.add_argument('-H','--host',action='store',default='localhost')
    parser.add_argument('-P','--port',action='store',type=int,default=14000)
    parser.add_argument('--coordinators',nargs="+", action='store')
    parser.add_argument('-v','--version', action='version', version='%(prog)s ' + version)
    parser.add_argument('-c','--critical', action='store', type=int, default=10)
    parser.add_argument('-w','--warning', action='store', type=int, default=10)
    parser.add_argument('--log_file',action='store',default='nagios/')
    args = parser.parse_args()
    if args.secure and (args.principal is None or args.keytab is None):
        parser.error("if secure cluster, both of --principal and --keytab required")
    return args

class Oozie(nagiosplugin.Resource):

    def __init__(self,args):
	f = open('/tmp/myfile','w')
	f.write('hi there\n') # python will convert \n to os.linesep
	f.close()
        params={}
        params['host'] = args.host
        params['port'] = args.port
        if args.principal:
            params['principal'] = args.principal
        if args.keytab:
            params['keytab'] = args.keytab
	params['cache_file'] = args.cache_file
	params['log_file'] = args.log_file
        params['secure'] = args.secure
        self.oozie_status=ooziestatus.OozieStatus(params)
        if args.coordinators is not None:
            self.coordinators=args.coordinators
        else:
            self.coordinators=self.oozie_status.coordinators.keys()
 
    def probe(self):
        for coord in self.coordinators:
            total = self.oozie_status.coordinators[coord]['total']
            if self.oozie_status.coordinators[coord].get('SUCCEEDED'):
                success =  float(self.oozie_status.coordinators[coord].get('SUCCEEDED').get('count')*100/total)
            else:
                success = 0.0
            if self.oozie_status.coordinators[coord].get('WAITING'):
                waiting =  float(self.oozie_status.coordinators[coord].get('WAITING').get('count')*100/total)
            else:
                waiting = 0.0
            fails = 100.0 - success - waiting
            yield nagiosplugin.Metric('Fails ' + coord, 100.0 ,context="errors") # - success - waiting,context="errors")

@nagiosplugin.guarded
def main():
    html_auth = None
    args = parser()
    check = nagiosplugin.Check(Oozie(args),
        nagiosplugin.ScalarContext('errors',
            args.warning,
            args.critical))
    check.main()

if __name__ == '__main__':
    main()
