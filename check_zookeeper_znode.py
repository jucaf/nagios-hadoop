#!/usr/bin/env python
# vim: ts=4:sw=4:et:sts=4:ai:tw=80
from utils import StringContext,krb_wrapper
import nagiosplugin
import argparse
import subprocess,os,re
import ast

def parser():
    version="0.1"
    parser = argparse.ArgumentParser(description="Check zookeeper znodes existence and content")
    parser.add_argument('-H','--hosts',action='store',required=True)
    parser.add_argument('-s','--secure',action='store_true')
    parser.add_argument('-p','--principal',action='store')
    parser.add_argument('-k','--keytab',action='store')
    parser.add_argument('-c','--cache_file',action='store',default='/tmp/nagios_zookeeper')
    parser.add_argument('-t','--test',action='store',required=True)
    parser.add_argument('-T','--topic',action='store')
    parser.add_argument('-z','--zk_client',action='store',default='/usr/bin/zookeeper-client')
    args = parser.parse_args()
    if args.secure and (args.principal is None or args.keytab is None):
        parser.error('If secure cluster, both of --principal and --keytab required')
    return args

class ZookeeperZnode(nagiosplugin.Resource):
    def call_zk(self,cmd,url):
        response = subprocess.Popen([self.zk_client,'-server', self.zkserver, cmd, url],stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output,err = response.communicate()
        return output.splitlines()[-1],err

    def __init__(self,args):
        self.zkserver = args.hosts
        self.zk_client = args.zk_client
        self.test = args.test
        self.tests = {'hdfs' : self.check_hdfs,
                'hbase' : self.check_hbase,
                'kafka' : self.check_kafka
        }
        self.topic=args.topic

    def probe(self):
        return self.tests[self.test]()
    
    def znode_exist(self,path):
        output,err = self.call_zk('stat',path)
        if err is None or re.match('^Node does not exist:\s*%s' % path,err) is None:
            return True
        else:
            return False

    def check_hdfs(self):
        return [nagiosplugin.Metric('ActiveNN lock', self.znode_exist('/hadoop-ha/hdfscluster/ActiveStandbyElectorLock'),context='true')]

    def check_hbase(self):
        return [ nagiosplugin.Metric('Hbase Master', self.znode_exist('/hbase/master'), context='true'),
            nagiosplugin.Metric('Failover', self.znode_exist('/hbase/backup-masters'), context='true'),
            nagiosplugin.Metric('Metaregion server', self.znode_exist('/hbase/meta-region-server'), context='true'),
            nagiosplugin.Metric('Unassigned', self.znode_exist('/hbase/unassigned'), context='false')]

    def check_kafka(self):
        metrics=[]
        self.topics,self.kafka_servers=self.get_kafka_state()
        for k_topic,v_topic in self.topics.iteritems():
            for k_partition,v_partition in v_topic.iteritems():
                all_sync=True
                for host in self.kafka_servers:
                    all_sync = False if not host in v_partition['isr'] else all_sync
                metrics.append(nagiosplugin.Metric('Topic %s partition %s in sync' % (k_topic, k_partition),all_sync,context='true'))
        return metrics

    def get_kafka_state(self):
        output,err=self.call_zk('ls','/brokers/ids')
        ids=ast.literal_eval(output)
        ids_parsed=dict()
        for host in ids:
            ids_parsed[host]=ast.literal_eval(self.call_zk('get','/brokers/ids/%d' % host)[0])
        if self.topic is not None:
            topics=[self.topic]
        else:
            output,err=self.call_zk('ls','/brokers/topics')
            topics=output.replace('[','').replace(']','').replace(',',' ').split()
        topics_parsed=dict()
        for topic in topics:
            output,err=self.call_zk('ls','/brokers/topics/%s/partitions' % topic)
            partitions=ast.literal_eval(self.call_zk('ls','/brokers/topics/%s/partitions' % topic)[0])
            partitions_parsed=dict()
            for partition in partitions:
                partitions_parsed[partition]=ast.literal_eval(self.call_zk('get','/brokers/topics/%s/partitions/%d/state' % (topic,partition))[0])
            topics_parsed[topic]=partitions_parsed
        return topics_parsed,ids_parsed
        
@nagiosplugin.guarded
def main():
    args = parser()
    if args.secure:
        auth_token = krb_wrapper(args.principal, args.keytab,args.cache_file)
        os.environ['KRB5CCNAME'] = args.cache_file
    check = nagiosplugin.Check(ZookeeperZnode(args),
        StringContext('true',True),
        StringContext('false',False))
    check.main()
    if args.secure: auth_token.destroy()

if __name__ == '__main__':
    main()