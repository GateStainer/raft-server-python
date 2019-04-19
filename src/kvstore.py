
import grpc
import kvstore_pb2
import kvstore_pb2_grpc
import random
from chaosmonkey import CMServer

class KVServer(kvstore_pb2_grpc.KeyValueStoreServicer):
    def __init__(self, addresses: list, id: int):
        self.storage = dict()
        self.addresses = addresses
        self.id = id
        self.cmserver = CMServer(num_server=len(addresses))
        print('Initial ChaosMonkey matrix:')
        print(self.cmserver)

    def localGet(self, key):
        resp = kvstore_pb2.GetResponse()
        try:
            resp.value = self.storage[key]
            resp.ret = kvstore_pb2.SUCCESS
            print(f'RAFT: localGet <{key}, {resp.value}>')
        except KeyError:
            resp.ret = kvstore_pb2.FAILURE
            print(f'RAFT: localGet failed, no such key: [{key}]')
        return resp

    def localPut(self, key, val):
        resp = kvstore_pb2.PutResponse()
        self.storage[key] = val
        resp.ret = kvstore_pb2.SUCCESS
        print(f'RAFT: localPut <{key}, {val}>')
        return resp

    def serverGet(self, request, context):
        print(f'RAFT: get a serverGet request')
        resp = self.localGet(request.key)
        if resp.ret == kvstore_pb2.SUCCESS:
            context.set_code(grpc.StatusCode.OK)
        else:
            context.set_code(grpc.StatusCode.CANCELLED)
        return resp

    def serverPut(self, request, context):
        print(f'RAFT: get a serverPut request, <{request.key}, {request.value}>')
        resp = self.localPut(request.key, request.value)
        if resp.ret == kvstore_pb2.SUCCESS:
            context.set_code(grpc.StatusCode.OK)
        else:
            context.set_code(grpc.StatusCode.CANCELLED)
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
            print(f'RAFT: serverGet from {addr}')
            with grpc.insecure_channel(addr) as channel:
                stub = kvstore_pb2_grpc.KeyValueStoreStub(channel)
                serverGetResp = stub.serverGet(kvstore_pb2.GetRequest(key=key))

                if serverGetResp.ret == kvstore_pb2.SUCCESS:
                    resp = kvstore_pb2.GetResponse(ret=kvstore_pb2.SUCCESS,
                                                   value=serverGetResp.value)
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
            print(f'RAFT: serverPut <{key}, {val}> to {addr}, fail rate {self.cmserver.fail_mat[self.id][idx]}')
            if random.uniform(0, 1) < self.cmserver.fail_mat[self.id][idx]:
                print(f'RAFT[ABORTED]: serverPut <{key}, {val}> to {addr}, because of ChaosMonkey')
                continue
            with grpc.insecure_channel(addr) as channel:
                try:
                    stub = kvstore_pb2_grpc.KeyValueStoreStub(channel)
                    req = kvstore_pb2.PutRequest(key=key, value=val)
                    serverPutResp = stub.serverPut(req)
                except Exception as e:
                    print(e)
        if resp.ret == kvstore_pb2.SUCCESS:
            context.set_code(grpc.StatusCode.OK)
        else:
            context.set_code(grpc.StatusCode.CANCELLED)
        return resp
