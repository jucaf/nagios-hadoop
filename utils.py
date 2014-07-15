#!/usr/bin/env python
# vim: ts=4:sw=4:et:sts=4:ai:tw=80

import krbV
import os
import nagiosplugin
import socket

class StringContext(nagiosplugin.Context):
    def __init__(self, name,value,level="critical",fmt_metric=None, result_cls=nagiosplugin.Result):
        super(StringContext, self).__init__(name, fmt_metric, result_cls)
        self.value=value
        self.level=level

    def evaluate(self, metric, resource):
        if self.value == metric.value:
            return self.result_cls(nagiosplugin.Ok,hint=metric.description,metric=metric)
        else:
            if self.level == "critical":
                return self.result_cls(nagiosplugin.Critical,hint=metric.description,metric=metric)
            else:
                return self.result_cls(nagiosplugin.Warn,hint=metric.description,metric=metric)

class krb_wrapper():
    def __init__(self,principal,keytab,ccache_file=None):
        self.context = krbV.default_context()
        self.principal = krbV.Principal(name=principal, context=self.context)
        self.keytab = krbV.Keytab(name=keytab, context=self.context)
        self.ccache_file = ccache_file
        if ccache_file:
            self.ccache_file = ccache_file
            self.ccache = krbV.CCache(name="FILE:" + self.ccache_file, context=self.context, primary_principal=self.principal)
        else:
            self.ccache = self.context.default_ccache(primary_principal=self.principal)
        self.ccache.init(self.principal)
        self.ccache.init_creds_keytab(keytab=self.keytab,principal=self.principal)

    def destroy(self):
        if self.ccache_file:
            os.system('kdestroy -c %s 2>/dev/null' % self.ccache_file)
        else:
            os.system('kdestroy 2>/dev/null')

    def reload(self):
        self.ccache.init(self.principal)
        self.ccache.init_creds_keytab(keytab=self.keytab,principal=self.principal)

def netcat(hostname, port, content):
    data = "" 
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((hostname, port))
    s.sendall(content)
    s.shutdown(socket.SHUT_WR)
    while 1:
        buff = s.recv(1024)
        if buff == "":
            break
        else:
            data += buff
    s.close()
    return data


