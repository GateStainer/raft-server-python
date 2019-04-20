
import grpc
import kvstore_pb2
import kvstore_pb2_grpc
import random
import logging
from chaosmonkey import CMServer

class KVServer(kvstore_pb2_grpc.KeyValueStoreServicer):
    def __init__(self, addresses: list, id: int):
        self.storage = dict()
        self.addresses = addresses
        self.id = id
        self.cmserver = CMServer(num_server=len(addresses))
        self.logger = logging.getLogger('raft')
        self.logger.info('Initial ChaosMonkey matrix:')
        print(self.cmserver)

    def localGet(self, key):
        resp = kvstore_pb2.GetResponse()
        try:
            resp.value = self.storage[key]
            resp.ret = kvstore_pb2.SUCCESS
            self.logger.info(f'RAFT: localGet <{key}, {resp.value}>')
        except KeyError:
            resp.ret = kvstore_pb2.FAILURE
            self.logger.warn(f'RAFT: localGet failed, no such key: [{key}]')
        return resp

    def localPut(self, key, val):
        resp = kvstore_pb2.PutResponse()
        self.storage[key] = val
        resp.ret = kvstore_pb2.SUCCESS
        self.logger.info(f'RAFT: localPut <{key}, {val}>')
        return resp

    def Get(self, request, context):
        key = request.key
        resp = self.localGet(key)
        if resp.ret == kvstore_pb2.SUCCESS:
            context.set_code(grpc.StatusCode.OK)
            return resp
        for idx, addr in enumerate(self.addresses):
            if idx == self.id:
                continue
            self.logger.info(f'RAFT: serverGet from {addr}')
            with grpc.insecure_channel(addr) as channel:
                stub = kvstore_pb2_grpc.KeyValueStoreStub(channel)
                append_resp = stub.appendEntries(kvstore_pb2.AppendRequest(type=kvstore_pb2.GET, key=key))

                if append_resp.ret == kvstore_pb2.SUCCESS:
                    resp = kvstore_pb2.GetResponse(ret=kvstore_pb2.SUCCESS,
                                                   value=append_resp.value)
                    context.set_code(grpc.StatusCode.OK)
                    return resp
        context.set_code(grpc.StatusCode.CANCELLED)
        return kvstore_pb2.GetRequest(ret=kvstore_pb2.FAILURE)

    def Put(self, request, context):
        key = request.key
        val = request.value
        resp = self.localPut(key, val)
        for idx, addr in enumerate(self.addresses):
            if idx == self.id:
                continue
            self.logger.info(f'RAFT: serverPut <{key}, {val}> to {addr}, fail rate {self.cmserver.fail_mat[self.id][idx]}')
            if random.uniform(0, 1) < self.cmserver.fail_mat[self.id][idx]:
                self.logger.warn(f'RAFT[ABORTED]: serverPut <{key}, {val}> to {addr}, because of ChaosMonkey')
                continue
            with grpc.insecure_channel(addr) as channel:
                try:
                    stub = kvstore_pb2_grpc.KeyValueStoreStub(channel)
                    append_resp = stub.appendEntries(kvstore_pb2.AppendRequest(type=kvstore_pb2.PUT, key=key, value=val))
                except Exception as e:
                    self.logger.error(e)
        if resp.ret == kvstore_pb2.SUCCESS:
            context.set_code(grpc.StatusCode.OK)
        else:
            context.set_code(grpc.StatusCode.CANCELLED)
        return resp

    def appendEntries(self, request, context):
        req_type = request.type
        if req_type == kvstore_pb2.HEARTBEAT:
            self.logger.info('RAFT: get a heartbeat')
            return kvstore_pb2.AppendResponse(ret = kvstore_pb2.SUCCESS, value='')
        elif req_type == kvstore_pb2.GET:
            self.logger.info(f'RAFT: get a GET log {request.key}')
            val = self.localGet(request.key)
            return kvstore_pb2.AppendResponse(ret = kvstore_pb2.SUCCESS, value=val)
        elif req_type == kvstore_pb2.PUT:
            self.logger.info(f'RAFT: get a PUT log <{request.key}, {request.value}>')
            self.logger.critical(f'WAL: <PUT, {request.key}, {request.value}>')
            return kvstore_pb2.AppendResponse(ret = kvstore_pb2.SUCCESS, value='')
        else:
            self.logger.error(f'RAFT: unknown entry')
            return kvstore_pb2.AppendResponse(ret = kvstore_pb2.FAILURE, value='')