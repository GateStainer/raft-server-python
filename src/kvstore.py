
import grpc

import kvstore_pb2
import kvstore_pb2_grpc


class KVServer(kvstore_pb2_grpc.KeyValueStoreServicer):
    def __init__(self, addresses: list, id: int):
        self.storage = dict()
        self.addresses = addresses
        self.id = id

    def localGet(self, key):
        resp = kvstore_pb2.GetResponse()
        try:
            resp.value = self.storage[key]
            resp.ret = kvstore_pb2.SUCCESS
        except KeyError:
            print(f'RAFT: Get failed, no such key: [{key}]')
            resp.ret = kvstore_pb2.FAILURE
        return resp

    def localPut(self, key, val):
        resp = kvstore_pb2.PutResponse()
        self.storage[key] = val
        resp.ret = kvstore_pb2.SUCCESS
        return resp

    def serverGet(self, request, context):
        resp = self.localGet(request.key)
        if resp.ret == kvstore_pb2.SUCCESS:
            context.set_code(grpc.StatusCode.OK)
        else:
            context.set_code(grpc.StatusCode.CANCELLED)
        return resp

    def serverPut(self, request, context):
        resp = self.localPut(request.key, request.val)
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
            print(f'RAFT: serverPut to {addr}')
            with grpc.insecure_channel(addr) as channel:
                stub = kvstore_pb2_grpc.KeyValueStoreStub(channel)
                serverPutResp = stub.serverPut(kvstore_pb2.PutRequest(key=key, value=val))
