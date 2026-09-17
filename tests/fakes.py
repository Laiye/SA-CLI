#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""伪 VISA 资源与通用 fixtures。"""

from pathlib import Path

import sa_cli.data


from sa_cli.instruments import Instrument

DATA_DIR = Path(sa_cli.data.__file__).parent
SA_JSON = str(DATA_DIR / "spectrum_analyzer.json")
SG_JSON = str(DATA_DIR / "signal_generator.json")


class FakeVisaResource:
    """记录 write/query 的伪 VISA 资源。"""

    def __init__(self, responses=None):
        self.timeout = 5000
        self.writes = []
        self.queries = []
        self.cleared = False
        self.responses = dict(responses or {})

    def write(self, command):
        self.writes.append(command)

    def clear(self):
        self.cleared = True

    def query(self, command):
        self.queries.append(command)
        if command in self.responses:
            return str(self.responses[command])
        if command == "*OPC?":
            return "1"
        return "OK"

    def close(self):
        pass


class FakeResourceManager:
    def __init__(self, resource=None):
        self.resource = resource or FakeVisaResource()
        self.closed = False

    def open_resource(self, address):
        return self.resource

    def close(self):
        self.closed = True


def build_instrument(json_file, responses=None, rm_resource=None):
    """构造一个使用伪 VISA 资源的 Instrument，返回 (instr, resource, rm)。"""
    resource = rm_resource or FakeVisaResource(responses)
    rm = FakeResourceManager(resource)
    instr = Instrument("dummy", json_file, rm=rm)
    return instr, resource, rm


