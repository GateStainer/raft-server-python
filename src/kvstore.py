import grpc
import kvstore_pb2
import kvstore_pb2_grpc
import random
import logging
import json
import time
import threading
from chaosmonkey import CMServer


class KVServer(kvstore_pb2_grpc.KeyValueStoreServicer):
    follower = 0
    candidate = 1
    leader = 2
    def __init__(self, addresses: list, id: int):
        self.id = id
        self.persistent_file = 'config-%d' % self.id
        # load persistent state from json file
        self.load()
        # volatile state on all: commitIndex, lastApplied
        # 0 for follower, 1 for candidate, 2 for leader
        self.role = KVServer.follower
        self.leaderID = 0
        self.commitIndex = 0
        self.lastApplied = 0
        self.peers = []
        for idx, addr in enumerate(addresses):
            if idx != self.id:
                self.peers.append(idx)
        self.majority = len(self.peers) / 2 + 1
        self.request_votes = self.peers[:]
        self.numVotes = 0
        self.oldVotes = 0
        self.newVotes = 0


        #TODO: move these to leader election
        # volatile state on leaders: nextIndex[], matchIndex[]
        self.nextIndex = []
        self.matchIndex =[] #known commit index on servers

        self.leader = -1 # leader = index in addresses
        self.requestTimeout = -1
        self.addresses = addresses # number of nodes implied here
        self.cmserver = CMServer(num_server=len(addresses))
        self.logger = logging.getLogger('raft')
        self.logger.info('Initial ChaosMonkey matrix:')
        print(self.cmserver)

    def follower(self):
        print('Running as a follower')
        self.role = KVServer.follower

        # TODO: Implement follower behaviour

    def load(self):
        # TODO: load persistent state from json file
        if self.persistent_file:
            with open(self.persistent_file, 'r') as f:
                datastore = json.load(f)
                self.currentTerm = datastore["currentTerm"]
                self.votedFor = datastore["votedFor"]
                # each entry in the list contains (term, <key, value>)
                self.log_entries = datastore["log_entries"]


    def save(self):
        #TODO: save persistent state to json file
        # If the file name exists, write a JSON string into the file.
        if self.persistent_file:
            # Writing JSON data
            persistent = {"currentTerm": self.currentTerm, "votedFor": self.votedFor, "log_entries": self.log_entries};
            with open(self.persistent_file, 'w') as f:
                json.dump(persistent, f)

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
            # zixuan
            # if random.uniform(0, 1) < self.cmserver.fail_mat[self.id][idx]:
            #     self.logger.warn(f'RAFT[ABORTED]: serverPut <{key}, {val}> to {addr}, because of ChaosMonkey')
            #     continue
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
        inc_server_id = request.incServerID
        req_type = request.type
        if req_type == kvstore_pb2.HEARTBEAT:
            self.logger.info('RAFT: get a heartbeat')
            return kvstore_pb2.AppendResponse(ret = kvstore_pb2.SUCCESS, value='')
        elif req_type == kvstore_pb2.GET:
            self.logger.info(f'RAFT: get a GET log {request.key}')
            val = self.localGet(request.key)
            return kvstore_pb2.AppendResponse(ret = kvstore_pb2.SUCCESS, value=val)
        elif req_type == kvstore_pb2.PUT:
            #mcip
            if random.uniform(0, 1) < self.cmserver.fail_mat[self.id][self.id]:
                self.logger.warn(f'RAFT[ABORTED]: serverPut <{key}, {val}> to {addr}, because of ChaosMonkey')
            else:
                #zixuan
                self.logger.info(f'RAFT: get a PUT log <{request.key}, {request.value}>')
                self.logger.critical(f'WAL: <PUT, {request.key}, {request.value}>')
                return kvstore_pb2.AppendResponse(ret = kvstore_pb2.SUCCESS, value='')
        else:
            self.logger.error(f'RAFT: unknown entry')
            return kvstore_pb2.AppendResponse(ret = kvstore_pb2.FAILURE, value='')

    def requestVote(self, request, context):
        reqTerm = request.term
        reqCandidateID = request.candidateID
        reqLastLogIndex = request.lastLogIndex
        reqLastLogTerm = request.lastLogTerm
        # self.lastApplied? or most recent commit index
        if reqLastLogTerm <= self.currentTerm or reqLastLogIndex<self.lastApplied or self.votedFor != -1:
            self.logger.info(f'RAFT: vote denied for server <{reqCandidateID}>')
            return kvstore_pb2.VoteRequest(term = self.currentTerm, voteGranted = False)
        else:
            self.logger.critical(f'RAFT: voted for <{reqCandidateID}>')
            self.votedFor = reqCandidateID
            self.currentTerm = reqTerm
            return kvstore_pb2.VoteRequest(term = self.currentTerm, voteGranted = True)

    def processVote(self):
        vote_request = kvstore_pb2.VoteRequest(term = self.currentTerm+1, candidateID = self.id,
                                               lastLogIndex = self.lastApplied, lastLogTerm = self.currentTerm)
        vote_count = 1
        for idx, addr in enumerate(self.addresses):
            if idx == self.id:
                continue
            try:
                with grpc.insecure_channel(addr) as channel:
                    stub = kvstore_pb2_grpc.KeyValueStoreStub(channel)
                    # Timeout error

                    request_vote_response = stub.requestVote(vote_request, timeout = 0.1) # timeout keyword ok?
                    if request_vote_response.voteGranted:
                        vote_count += 1
            except Exception as e:
                self.logger.error(e)






