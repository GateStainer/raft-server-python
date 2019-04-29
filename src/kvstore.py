import grpc
import kvstore_pb2
import kvstore_pb2_grpc
import random
import logging
import json
import time
import os
import pickle as pkl
import threading
from KThread import *
from chaosmonkey import CMServer


class KVServer(kvstore_pb2_grpc.KeyValueStoreServicer):
    follower = 0
    candidate = 1
    leader = 2
    def __init__(self, addresses: list, id: int, server_config: dict):
        self.requestTimeout = server_config["request_timeout"] # in ms
        self.electionTimeout = server_config["election_timeout"]
        self.keySizeLimit = server_config["key_size"]
        self.valSizeLimit = server_config["value_size"]

        self.id = id
        self.persistent_file = 'config-%d' % self.id
        # load persistent state from json file
        self.load()

        self.diskData = "data-%d.pkl" % self.id

        #volatile state
        self.role = KVServer.follower
        self.leaderID = 0
        self.commitIndex = 0
        self.lastApplied = 0
        self.peers = []

        # current state
        self.curEleTimeout = float(random.randint(self.electionTimeout/2, self.electionTimeout)/1000) # in sec
        for idx, addr in enumerate(addresses):
            if idx != self.id:
                self.peers.append(idx)
        self.majority = len(self.peers) / 2 + 1
        self.request_votes = self.peers[:]
        self.newVotes = 0
        self.lastLogIndex = 0
        self.lastLogTerm = 0
        self.addresses = addresses # number of nodes implied here
        self.cmserver = CMServer(num_server=len(addresses))
        self.logger = logging.getLogger('raft')
        self.logger.info('Initial ChaosMonkey matrix:')
        print(self.cmserver)

    def load(self):
        # TODO: load persistent state from json file
        self.currentTerm = 0
        self.votedFor = -1
        # each entry in the list contains (term, <key, value>)
        self.log_entries = []
        if os.path.isfile(self.persistent_file):
            with open(self.persistent_file, 'r') as f:
                datastore = json.load(f)
                self.currentTerm = datastore["currentTerm"]
                self.votedFor = datastore["votedFor"]
                # TODO: each entry in the list contains (term, key, value)
                self.log_entries = datastore["log_entries"]

    def save(self):
        #TODO: save persistent state to json file
        # Writing JSON data
        persistent = {"currentTerm": self.currentTerm, "votedFor": self.votedFor, "log_entries": self.log_entries}
        with open(self.persistent_file, 'w') as f:
            json.dump(persistent, f)

    def follower(self):
        print('Running as a follower')
        self.role = KVServer.follower
        self.last_update = time.time()
        # TODO: Change election timeout here
        # election_timeout = 5 * random.random() + 5
        while time.time() - self.last_update <= self.curEleTimeout:
            pass
        self.start_election()
        while True:
            self.last_update = time.time()
            # TODO: Change election timeout here
            # election_timeout = 5 * random.random() + 5
            self.curEleTimeout = float(random.randint(self.electionTimeout/2, self.electionTimeout)/1000)
            while time.time() - self.last_update <= self.curEleTimeout:
                pass
            # kill old election thread
            if self.election.is_alive():
                self.election.kill()
            self.start_election()

    def start_election(self):
        # Create a new thread for leader election
        print("Start leader election")
        self.role = KVServer.candidate
        self.currentTerm += 1
        self.votedFor = self.id
        self.save()
        self.numVotes = 1
        self.election = KThread(target = self.initiateVote, args = ())
        self.election.start()

    def requestVote(self, request, context): # receiving side
        reqTerm = request.term
        reqCandidateID = request.candidateID
        reqLastLogIndex = request.lastLogIndex
        reqLastLogTerm = request.lastLogTerm
        print(f'Receive request vote from <{reqCandidateID}>')
        # TODO: Update requestVote Rules
        if reqTerm < self.currentTerm or reqLastLogTerm < self.lastLogTerm or reqLastLogIndex < self.lastLogIndex or \
                (self.votedFor != -1 and self.votedFor != reqCandidateID):
            votegranted = False
        elif reqTerm == self.currentTerm:
            # TODO: Add lock here
            votegranted = True
            self.votedFor = reqCandidateID
            self.save()
        # Find higher term in RequestVote message
        else:
            self.currentTerm = reqTerm
            self.save()
            self.step_down()
            votegranted = True
            self.votedFor = reqCandidateID
            self.save()
        return kvstore_pb2.VoteResponse(term = self.currentTerm, voteGranted = votegranted)
            # self.logger.info(f'RAFT: vote denied for server <{reqCandidateID}>')
            # self.logger.critical(f'RAFT: voted for <{reqCandidateID}>')

    def initiateVote(self):
        for idx, addr in enumerate(self.addresses):
            if idx == self.id:
                continue
            # Create a thread for each request vote
            election_thread = KThread(target = self.thread_election, args = (idx, addr, ))
            election_thread.start()

    def thread_election(self, idx, addr):
        vote_request = kvstore_pb2.VoteRequest(term = self.currentTerm, candidateID = self.id,
                                               lastLogIndex = self.lastLogIndex, lastLogTerm = self.lastLogTerm)
        try:
            with grpc.insecure_channel(addr) as channel:
                stub = kvstore_pb2_grpc.KeyValueStoreStub(channel)
                print(f'Send vote request to <{idx}>')
                # Timeout error
                request_vote_response = stub.requestVote(
                    vote_request, timeout = self.requestTimeout) # timeout keyword ok?
                if request_vote_response.voteGranted:
                    print(f'vote received from <{idx}>')
                else:
                    print(f'vote rejected from <{idx}>')
                # if I receive voteGranted
                # TODO: Add lock here to consider concurrency
                if request_vote_response.voteGranted:
                    if self.role == KVServer.candidate:
                        self.numVotes += 1
                        if self.numVotes == self.majority:
                            self.role = KVServer.leader
                            print("Become Leader")
                            # kill election and follower thread
                            if self.election.is_alive():
                                self.election.kill()
                            self.follower_state.kill()
                            # Create a thread for leader thread
                            self.leader_state = KThread(target = self.leader, args = ())
                            self.leader_state.start()
                else:
                    # discover higher term
                    if request_vote_response.term > self.currentTerm:
                        self.currentTerm = request_vote_response.term
                        self.save()
                        self.step_down()
        except Exception as e:
            self.logger.error(e)

    # Leader or Candidate steps down to follower
    def step_down(self):
        if self.role == KVServer.candidate:
            print("Candidate step down when higher term")
            self.election.kill()
            self.last_update = time.time()
            self.role = KVServer.follower
        elif self.role == KVServer.leader:
            self.leader_state.kill()
            self.follower_state = KThread(target = self.follower, args = ())
            self.follower_state.start()

    def leader(self):
        print("Running as a leader")
        self.role = KVServer.leader
        # volatile state on leaders: nextIndex[], matchIndex[]
        self.nextIndex = {}
        self.matchIndex ={} #known commit index on servers
        for peer in self.peers:
            self.nextIndex[peer] = len(self.log_entries) + 1
            self.matchIndex[peer] = 0
        self.append_entries()

    # Leader sends append_entry message as log replication and heart beat
    def append_entries(self):
        while True:
            for idx, addr in enumerate(self.addresses):
                if idx == self.id:
                    continue
                # Create a thread for each append_entry message
                append_thread = KThread(target = self.thread_append_entry, args = (idx, addr, ))
                append_thread.start()
            # heart beat
            time.sleep(0.5)

    def thread_append_entry(self, idx, addr):
        append_request = kvstore_pb2.AppendRequest()
        if len(self.log_entries) >= self.nextIndex[idx]:
            prevLogIndex = self.nextIndex[idx] - 1
            if prevLogIndex != 0:
                prevLogTerm = self.log_entries[prevLogIndex-1].term
            else:
                prevLogTerm = 0
            entries = [self.log_entries[self.nextIndex[idx]-1]]
        else:
            entries = []
            prevLogIndex = len(self.log_entries)
            if prevLogIndex != 0:
                prevLogTerm = self.log_entries[prevLogIndex-1].term
            else:
                prevLogTerm = 0
        append_request.term = self.currentTerm
        append_request.leaderID = self.id
        append_request.prevLogIndex = prevLogIndex
        append_request.prevLogTerm = prevLogTerm
        append_request.leaderCommit = self.commitIndex
        append_request.incServerID = self.id
        for temp_entry in entries:
            entry = append_request.entries.add()
            entry.term = temp_entry.term
            entry.log.key = temp_entry.log.key
            entry.log.value = temp_entry.log.value
        try:
            with grpc.insecure_channel(addr) as channel:
                stub = kvstore_pb2_grpc.KeyValueStoreStub(channel)
                print(f'Send append_entry to <{idx}>')
                append_entry_response = stub.appendEntries(
                    append_request, timeout = self.requestTimeout)
                # TODO: Implement append entry response
        except Exception as e:
            self.logger.error(e)

    def appendEntries(self, request, context): # receiving/server side
        # TODO: Implement appendEntries gRPC
        inc_server_id = request.incServerID
        req_type = request.type
        if random.uniform(0, 1) < self.cmserver.fail_mat[inc_server_id][self.id]:
            self.logger.warn(f'RAFT[ABORTED]: append entries from server <{inc_server_id}> '
                             f'to <{self.id}>, because of ChaosMonkey')
        else:
            self.last_update = time.time()
            # heartbeat, get, put or error
            if req_type == kvstore_pb2.HEARTBEAT:
                self.logger.info('RAFT: get a heartbeat')
                return kvstore_pb2.AppendResponse(ret = kvstore_pb2.SUCCESS, value='')
            # elif req_type == kvstore_pb2.GET: #TODO: no need to get? but can use readWithKey
            #     self.logger.info(f'RAFT: get a GET log {request.key}')
            #     val = self.localGet(request.key)
            #     return kvstore_pb2.AppendResponse(ret = kvstore_pb2.SUCCESS, value=val)
            elif req_type == kvstore_pb2.PUT:
                # commit to disk
                if request.leaderCommit > self.commitIndex:
                    self.commitIndex = request.leaderCommit
                    KThread(target = self.writeToDisk, args = ())
                self.logger.info(f'RAFT: get a PUT log <{request.key}, {request.value}>')
                self.logger.critical(f'WAL: <PUT, {request.key}, {request.value}>')
                return kvstore_pb2.AppendResponse(ret = kvstore_pb2.SUCCESS, value='')
            else:
                self.logger.error(f'RAFT: unknown entry')
                return kvstore_pb2.AppendResponse(ret = kvstore_pb2.FAILURE, value='')

    def writeToDisk(self):
        with open(self.diskData, 'wb') as f:
            pkl.dump(self.log_entries[self.commitIndex-self.lastApplied], f)
        self.log_entries = self.log_entries[self.commitIndex-self.lastApplied:] # TODO: async issues?
        self.lastApplied = self.commitIndex

    def readWithKey(self, key):
        n = len(self.log_entries)
        for i in range(n-1, -1, -1):
            if self.log_entries[i][1] == key: return self.log_entries[i][2]
        tmp_list = []
        with open(self.diskData, 'wb') as f:
            tmp_list = pkl.load(f)
        for i in range(len(tmp_list)-1, -1, -1):
            if tmp_list[i][1] == key: return tmp_list[i][2]
        return ""

    def run(self):
        # Create a thread to run as follower
        self.follower_state = KThread(target = self.follower, args = ())
        self.follower_state.start()


    # Checkpoint 1 Get Put Methods
    def localGet(self, key):
        val = self.readWithKey(key)
        if val == "": return kvstore_pb2.GetResponse(ret = kvstore_pb2.FAILURE, value = val)
        else: return kvstore_pb2.GetResponse(ret = kvstore_pb2.SUCCESS, value = val)
        # zixuan
        # try:
        #     resp.value = self.storage[key]
        #     resp.ret = kvstore_pb2.SUCCESS
        #     self.logger.info(f'RAFT: localGet <{key}, {resp.value}>')
        # except KeyError:
        #     resp.ret = kvstore_pb2.FAILURE
        #     self.logger.warn(f'RAFT: localGet failed, no such key: [{key}]')
        # return resp

    def localPut(self, key, val):
        resp = kvstore_pb2.PutResponse()
        self.storage[key] = val
        resp.ret = kvstore_pb2.SUCCESS
        self.logger.info(f'RAFT: localPut <{key}, {val}>')
        return resp

    def Get(self, request, context):
        # Asyncio implementation
        # https://github.com/grpc/grpc/issues/16329
        # def getProcessResponse(append_resp):
        #     if append_resp.ret == kvstore_pb2.SUCCESS:
        #         resp = kvstore_pb2.GetResponse(ret=kvstore_pb2.SUCCESS,
        #                                        value=append_resp.value)
        #         context.set_code(grpc.StatusCode.OK)
        #         return resp
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
                # Asyncio implementation
                # stub = kvstore_pb2_grpc.KeyValueStoreStub(channel)
                # append_resp = stub.appendEntries.future(kvstore_pb2.AppendRequest(type=kvstore_pb2.GET, key=key))
                # append_resp.add_done_callback(getProcessResponse)
                stub = kvstore_pb2_grpc.KeyValueStoreStub(channel)
                append_resp = stub.appendEntries(kvstore_pb2.AppendRequest(
                    type=kvstore_pb2.GET, key=key), timeout = self.requestTimeout) # timeout?
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
                    append_resp = stub.appendEntries(kvstore_pb2.AppendRequest(
                        type=kvstore_pb2.PUT, key=key, value=val), timeout = self.requestTimeout)
                except Exception as e:
                    self.logger.error(e)
        if resp.ret == kvstore_pb2.SUCCESS:
            context.set_code(grpc.StatusCode.OK)
        else:
            context.set_code(grpc.StatusCode.CANCELLED)
        return resp






