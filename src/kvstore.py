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
        # TODO: All log entries, only append when leader receives entries in put, also change lastLogIndex
        ### Persistent state on all servers
        self.currentTerm = 0
        self.votedFor = -1
        self.log = []

        # Todo: append to existing log
        # load persistent state from json file
        self.id = id
        self.persistent_file = 'config-%d' % self.id
        self.diskData = "data-%d.pkl" % self.id
        # Todo: will use load later
        # self.load()
        self.storage = {}
        # Config
        self.requestTimeout = server_config["request_timeout"]  # in ms
        self.electionTimeout = server_config["election_timeout"]
        self.keySizeLimit = server_config["key_size"]
        self.valSizeLimit = server_config["value_size"]

        ### Volatile state on all servers
        self.commitIndex = -1  # known to be commited
        self.lastApplied = -1  # index of highest log entry applied to state machine
        self.role = KVServer.follower
        self.leaderID = -1
        self.committedIndex = -1
        self.peers = []

        # current state
        self.curEleTimeout = float(random.randint(self.electionTimeout / 2, self.electionTimeout) / 1000)  # in sec
        for idx, addr in enumerate(addresses):
            if idx != self.id:
                self.peers.append(idx)
        self.majority = int(len(addresses) / 2) + 1
        print(self.majority)
        # self.request_votes = self.peers[:]
        self.lastLogIndex = -1
        self.lastLogTerm = 0
        self.addresses = addresses  # number of nodes implied here
        self.cmserver = CMServer(num_server=len(addresses))
        logging.basicConfig(filename='logger-%d' % self.id,
                            filemode='a',
                            format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                            datefmt='%H:%M:%S',
                            level=logging.DEBUG)
        self.logger = logging.getLogger('raft')
        self.logger.info('Initial ChaosMonkey matrix:')
        print(self.cmserver)

        ### Volatile state on leaders
        self.nextIndex = [0] * len(addresses)  # index of next log entry to send to that server
        self.matchIndex = [-1] * len(addresses)  # highest log entry known to be replicated

        self.debug1 = 0

    def load(self):
        self.votedFor = -1
        if os.path.isfile(self.persistent_file):
            with open(self.persistent_file, 'r') as f:
                datastore = json.load(f)
                self.currentTerm = datastore["currentTerm"]
                self.votedFor = datastore["votedFor"]

    def save(self):
        # TODO: check if all currentTerm and votedFor has .save() save persistent state to json file
        persistent = {"currentTerm": self.currentTerm, "votedFor": self.votedFor}
        with open(self.persistent_file, 'w') as f:
            json.dump(persistent, f)

    def follower(self):
        self.logger.critical(f'RAFT: Running as a follower')
        self.role = KVServer.follower
        self.last_update = time.time()
        while time.time() - self.last_update <= self.curEleTimeout:
            pass
        self.start_election()
        while True:
            self.last_update = time.time()
            self.curEleTimeout = float(random.randint(self.electionTimeout / 2, self.electionTimeout) / 1000)
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
        self.election = KThread(target=self.initiateVote, args=())
        self.election.start()

    def initiateVote(self):
        for idx, addr in enumerate(self.addresses):
            if idx == self.id:
                continue
            # Create a thread for each request vote
            election_thread = KThread(target=self.thread_election, args=(idx, addr,))
            election_thread.start()

    def thread_election(self, idx, addr):
        vote_request = kvstore_pb2.VoteRequest(term=self.currentTerm, candidateID=self.id,
                                               lastLogIndex=self.lastLogIndex, lastLogTerm=self.lastLogTerm)
        try:
            with grpc.insecure_channel(addr) as channel:
                stub = kvstore_pb2_grpc.KeyValueStoreStub(channel)
                print(f'Send vote request to <{idx}>')
                # Timeout error
                req_vote_resp = stub.requestVote(
                    vote_request, timeout=self.requestTimeout)  # timeout keyword ok?
                print(req_vote_resp.voteGranted, req_vote_resp.term)
                # if I receive voteGranted
                # TODO: Add lock here to consider concurrency
                self.nextIndex[req_vote_resp.serverID] = req_vote_resp.lastLogIndex
                self.matchIndex[req_vote_resp.serverID] = req_vote_resp.lastCommitIndex
                if req_vote_resp.voteGranted:
                    print(f'vote received from <{idx}>, <{self.majority}>')
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
                            self.leader_state = KThread(target=self.leader, args=())
                            self.leader_state.start()
                else:
                    print(f'vote rejected from <{idx}>')
                    # discover higher term
                    if req_vote_resp.term > self.currentTerm:
                        self.currentTerm = req_vote_resp.term
                        self.save()
                        self.step_down()
        except Exception as e:
            print(e)

    # Leader or Candidate steps down to follower
    def step_down(self):
        if self.role == KVServer.candidate:
            print("Candidate step down when higher term")
            self.election.kill()
            self.last_update = time.time()
            self.role = KVServer.follower
        elif self.role == KVServer.leader:
            self.leader_state.kill()
            self.follower_state = KThread(target=self.follower, args=())
            self.follower_state.start()

    def leader(self):
        self.logger.critical(f'RAFT: Running as a leader')
        self.role = KVServer.leader
        # volatile state on leaders: nextIndex[], matchIndex[]
        # self.nextIndex = {}
        # self.matchIndex ={} #known commit index on servers
        # for peer in self.peers:
        #     self.nextIndex[peer] = len(self.log) + 1
        #     self.matchIndex[peer] = 0
        # Todo: testing could be done here
        self.debug1 += 1
        self.log.append([self.debug1, "aa", "bb"])
        self.log.append([self.debug1, "aa", "bb"])
        self.lastLogIndex +=2
        self.lastLogTerm +=2
        self.append_entries()

    # Leader sends append_entry message as log replication and heart beat
    def append_entries(self):
        while True:
            for idx, addr in enumerate(self.addresses):
                if idx == self.id:
                    continue
                # Create a thread for each append_entry message
                append_thread = KThread(target=self.thread_append_entry, args=(idx, addr,))
                append_thread.start()
            # heart beat
            time.sleep(0.5)

    def debugLogging(self, toadd):
        print("executed")
        with open("debug.txt", 'w+') as f:
            data = json.load(f)
            data.append(toadd)
        json.dump(data, f)

    def thread_append_entry(self, idx, addr):
        append_request = kvstore_pb2.AppendRequest()
        append_request.term = self.currentTerm  # int32 term = 1;
        append_request.leaderID = self.id  # int32 leaderID = 2;
        append_request.prevLogIndex = self.nextIndex[idx]  # int32 prevLogIndex = 3;
        append_request.prevLogTerm = 0  # int32 prevLogTerm = 4;
        if 0 <= self.nextIndex[idx] < len(self.log):
            append_request.prevLogTerm = self.log[self.nextIndex[idx]][0]
        append_request.leaderCommit = self.commitIndex  # int32 leaderCommit = 6;
        last_req_log_idx = self.lastLogIndex
        # for row in self.log[0:]:  # repeated LogEntry entries = 5;
        #     entry = append_request.entries.add()
        #     entry.term = row[0]
        #     entry.key = row[1]
        #     entry.val = row[2]
        if self.nextIndex[idx] < len(self.log):
            for row in self.log[self.nextIndex[idx]:]:  # repeated LogEntry entries = 5;
                entry = append_request.entries.add()
                entry.term = row[0]
                entry.key = row[1]
                entry.val = row[2]
            self.nextIndex[idx] = self.lastLogIndex + 1
        try:
            with grpc.insecure_channel(addr) as channel:
                # int32 term = 1;
                # bool success = 2;
                # int32 committedIndex = 3;
                stub = kvstore_pb2_grpc.KeyValueStoreStub(channel)
                if random.uniform(0, 1) < self.cmserver.fail_mat[self.leaderID][self.id]:
                    print("Chaos Monkey blocking")
                    self.logger.warn(f'RAFT[ABORTED]: we will not receive from <{self.leaderID}> '
                                     f', because of ChaosMonkey')
                else:
                    print(f'Send append_entry to <{idx}>')
                    append_entry_response = stub.appendEntries(
                        append_request, timeout=self.requestTimeout)
                    # TODO: write to disk upon majority
                    # TODO: Implement append entry response
                    print("thread_append_entry response received")
                    if not append_entry_response.success:
                        # Failed since another server is leader now
                        if append_entry_response.term > self.currentTerm:
                            self.currentTerm = append_entry_response.term
                            self.save()
                            self.step_down()
                        # Failed because of log inconsistency, decrement nextIndex and retry
                        else:
                            self.nextIndex[idx] = self.matchIndex[idx]+1 #Todo: how to decrement correctly
                    # Success
                    else:
                        self.matchIndex[idx] = last_req_log_idx
                        n_list = sorted(self.matchIndex)
                        # if there exists such N that N> commitIndex and majority of matchIndex[i] >= N
                        # and log[N].term ==currentTerm, set commitIndex = N
                        N = n_list[int(len(n_list) / 2)]
                        if N >= 0 and N > self.commitIndex and self.log[N][0] == self.currentTerm:
                            self.commitIndex = N
                            writeToDiskKTh = KThread(target=self.writeToDisk, args=())
                            writeToDiskKTh.start()
        except Exception as e:
            self.logger.error(e)

    # mcip
    def appendEntries(self, request, context):  # receiving/server side
        # int32 term = 1;
        # int32 leaderID = 2;
        # int32 prevLogIndex = 3;
        # int32 prevLogTerm = 4;
        # repeated LogEntry entries = 5;
        # int32 leaderCommit = 6;
        # TODO: Implement appendEntries gRPC
        # return kvstore_pb2.AppendResponse(term = self.currentTerm, success = True)
        inc_server_id = request.leaderID
        if random.uniform(0, 1) < self.cmserver.fail_mat[inc_server_id][self.id]:
            self.logger.warn(f'RAFT[ABORTED]: append entries from server <{inc_server_id}> '
                             f'to <{self.id}>, because of ChaosMonkey')
        else:
            try:
                # self.logger.info("Received appendEntries")
                success = False
                self.last_update = time.time()
                # TODO: doesnt contain an entry at prevLogIndex whose term matches prevLogTerm
                tmp_entries = []
                for row in request.entries:
                    r = [row.term, row.key, row.val]
                    tmp_entries.append(r)
                    # self.logger.info(f'row: <{r}>')
                # reply false if term < currentTerm,
                # or log doesn't log doesn't contain an entry at prevLogIndex whose term matches prevLogTerm
                if request.term < self.currentTerm or request.prevLogIndex > self.lastLogIndex + 1 or \
                        (request.prevLogIndex < len(self.log) and
                         self.log[request.prevLogIndex][0] != request.prevLogTerm):
                    success = False
                    self.logger.warning(f'RAFT: appendEntries received on server <{self.id}> and will return false; '
                                        f'req term: <{request.term}>, cur term: <{self.currentTerm}, '
                                        f'req prevLogIdx: <{request.prevLogIndex}, lastLogIdx: <{self.lastLogIndex}>, '
                                        )
                else:
                    # self.logger.info("RAFT: AppendEntries should succeed unless there is conflict entries")
                    success = True
                    #     existing entry conflicts with a new one, same idx different terms,
                    #     delete the existing entry and all that follow it
                    # self.logger.info(f'RAFT: checking conflicting entries')
                    itr = 0
                    if len(self.log) > 0:
                        for a, b in zip(tmp_entries, self.log[request.prevLogIndex:]):
                            if a != b:
                                self.logger.warning(f'RAFT: Found conflict at index <{request.prevLogIndex + itr}>')
                                self.log = self.log[:request.prevLogIndex + itr]
                                return kvstore_pb2.AppendResponse(term=self.currentTerm, success=False)
                            itr += 1
                    self.logger.info("RAFT: Append entries from server")
                    # return kvstore_pb2.AppendResponse(term = self.currentTerm, success = success,
                    #                                   alreadyCommitted = self.alreadyCommitted)
                    # Heartbeat
                    if len(tmp_entries) == 0:
                        pass
                    # Normal append entries
                    else:
                        # Append any new entries not already in the log
                        # Todo: check if last log index is updated for every update of log[]
                        to_append_length = request.prevLogIndex + len(tmp_entries) - len(self.log)
                        self.logger.info(f'RAFT: length of log to append: <{to_append_length}>')
                        if to_append_length > 0:
                            self.log += tmp_entries[-to_append_length:]
                            self.lastLogIndex += to_append_length
                            # self.logger.info(f'debug: <{self.lastLogIndex}>, <{len(self.log)}>')
                            self.lastLogTerm = self.log[self.lastLogIndex][0]
                            self.logger.info(f'RAFT: Server log index: <{self.lastLogIndex}>; '
                                             f'Server log updated to: <{self.log}>')
                        # If leaderCommit > commitIndex, set commitIndex = min(leaderCommit, index of last new entry)
                        # print("Received log from appendEntries is: ", tmp_entries)
                        if request.leaderCommit > self.commitIndex:
                            self.commitIndex = min(request.leaderCommit, self.lastLogIndex)
                            writeToDiskKTh = KThread(target=self.writeToDisk, args=())
                            writeToDiskKTh.start()
                    # int32 term = 1;
                    # bool success = 2;
                    # int32 alreadyCommitted = 3;
            except Exception as e:
                self.logger.error(e)
            return kvstore_pb2.AppendResponse(term=self.currentTerm, success=success)
                # alreadyCommitted = self.alreadyCommitted)




    def writeToDisk(self):
        # TODO: maybe we can append only? maybe we need synchronization
        to_write = self.log[:self.commitIndex]
        with open(self.diskData, 'wb') as f:
            pkl.dump(to_write, f)
        self.committedIndex = self.commitIndex

    # Todo: read from dictionary instead using STORAGE
    def readWithKey(self, key):
        n = len(self.log)
        for i in range(n - 1, -1, -1):
            if self.log[i][1] == key: return self.log[i][2]
        return ""

    def run(self):
        # Create a thread to run as follower
        self.follower_state = KThread(target=self.follower, args=())
        self.follower_state.start()

    # Checkpoint 1 Get Put Methods
    def localGet(self, key):
        '''
        val = self.readWithKey(key)
        if val == "": return kvstore_pb2.GetResponse(ret = kvstore_pb2.FAILURE, value = val)
        else: return kvstore_pb2.GetResponse(ret = kvstore_pb2.SUCCESS, value = val)
        '''
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
        self.storage[key] = val  # dictionary
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
        else:
            context.set_code(grpc.StatusCode.CANCELLED)
            return resp
        '''
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
        '''

    def Put(self, request, context):
        # TODO: update last log index on leader
        # Todo: if command received from client: append entry to local log, respond after entry applied to state machine
        key = request.key
        val = request.value
        self.lastLogIndex += 1
        resp = self.localPut(key, val)
        cur_log = [self.currentTerm, key, val]
        self.log.append(cur_log)
        self.save()
        '''
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
        '''
        return resp

        # def appendEntries(self, request, context):
        #
        #     entries = request.entries
        #     leaderCommit = request.leaderCommit
        #     prevLogTerm = request.prevLogTerm
        #     prevLogIndex = request.prevLogIndex
        #     matchIndex = self.commitIndex
        #     # a valid new leader
        #     if request.term >= self.currentTerm:
        #         self.currentTerm = request.term
        #         self.save()
        #         self.step_down()
        #         if self.role == KVServer.follower:
        #             self.last_update = time.time()
        #         if prevLogIndex != 0:
        #             if len(self.log_entries) >= prevLogIndex:
        #                 if self.log_entries[prevLogIndex-1].term == prevLogTerm:
        #                     success = True
        #                     self.leaderID = request.leaderID
        #                     if len(entries) != 0:
        #                         self.log_entries = self.log_entries[:prevLogIndex] + entries
        #                         matchIndex = len(self.log_entries)
        #                 else:
        #                     success = False
        #         else:
        #             success = True
        #             if len(entries) != 0:
        #                 self.log_entries = self.log_entries[:prevLogIndex] + entries
        #                 self.save()
        #                 matchIndex = len(self.log_entries)
        #             self.leaderID = request.leaderID
        #     else:
        #         success = False
        #     if leaderCommit > self.commitIndex:
        #         lastApplied = self.commitIndex
        #         self.commitIndex = min(leaderCommit, len(self.log_entries))
        #         if self.commitIndex > lastApplied:
        #             for idx in range(1, self.commitIndex + 1):
        #                 self.storage[self.log_entries[idx-1].key] = self.log_entries[idx-1].value
        # return kvstore_pb2.AppendResponse(term = self.currentTerm, success = success, matchIndex = matchIndex)
        # pass

        # TODO: Implement appendEntries gRPC
        '''
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
            if random.uniform(0, 1) < self.cmserver.fail_mat[inc_server_id][self.id]:
                self.logger.warn(f'RAFT[ABORTED]: append entries from server <{inc_server_id}> '
                                 f'to <{self.id}>, because of ChaosMonkey')
            else:
                #zixuan
                self.logger.info(f'RAFT: get a PUT log <{request.key}, {request.value}>')
                self.logger.critical(f'WAL: <PUT, {request.key}, {request.value}>')
                return kvstore_pb2.AppendResponse(ret = kvstore_pb2.SUCCESS, value='')
        else:
            self.logger.error(f'RAFT: unknown entry')
            return kvstore_pb2.AppendResponse(ret = kvstore_pb2.FAILURE, value='')
        '''

    def requestVote(self, request, context):
        reqTerm = request.term
        reqCandidateID = request.candidateID
        reqLastLogIndex = request.lastLogIndex
        reqLastLogTerm = request.lastLogTerm
        print(f'Receive request vote from <{reqCandidateID}>')

        # TODO: Update requestVote Rules
        if reqTerm < self.currentTerm:
            votegranted = False
        elif reqTerm == self.currentTerm:
            # TODO: Add lock here
            if reqLastLogTerm >= self.lastLogTerm and reqLastLogIndex >= self.lastLogIndex \
                    and (self.votedFor == -1 or self.votedFor == reqCandidateID):
                votegranted = True
                self.votedFor = reqCandidateID
                self.save()
            else:
                votegranted = False
        # Find higher term in RequestVote message
        else:
            self.currentTerm = reqTerm
            self.save()
            self.step_down()
            if reqLastLogTerm >= self.lastLogTerm and reqLastLogIndex >= self.lastLogIndex:
                votegranted = True
                self.votedFor = reqCandidateID
                self.save()
            else:
                votegranted = False
        return kvstore_pb2.VoteResponse(term=self.currentTerm, voteGranted=votegranted)

    # mcip

    # def requestVote(self, request, context): # receiving vote request
    #     reqTerm = request.term
    #     reqCandidateID = request.candidateID
    #     reqLastLogIndex = request.lastLogIndex
    #     reqLastLogTerm = request.lastLogTerm
    #     print(f'Receive request vote from <{reqCandidateID}>')
    #     # TODO: Update requestVote Rules
    #     if reqTerm < self.currentTerm or reqLastLogTerm < self.lastLogTerm or reqLastLogIndex < self.lastLogIndex :
    #             # (self.votedFor != -1 and self.votedFor != reqCandidateID):
    #         # print(self.votedFor, (self.votedFor != -1 and self.votedFor != reqCandidateID))
    #         votegranted = False
    #     # Find higher term in RequestVote message
    #     else:
    #         votegranted = True
    #         self.currentTerm = reqTerm
    #         self.save()
    #         self.step_down()
    #         self.votedFor = reqCandidateID
    #         self.save()
    #         # int32 serverID = 1;
    #         # int32 term = 2;
    #         # int32 lastLogIndex = 3;
    #         # int32 lastCommitIndex = 4;
    #         # bool voteGranted = 5;
    #     return kvstore_pb2.VoteResponse(serverID = self.id, term = self.currentTerm, lastLogIndex = \
    #         self.lastLogIndex, lastCommitIndex = self.lastApplied, voteGranted = votegranted)
    #     # self.logger.info(f'RAFT: vote denied for server <{reqCandidateID}>')
    #     # self.logger.critical(f'RAFT: voted for <{reqCandidateID}>')
