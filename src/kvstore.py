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
from threading import Condition
from enum import Enum
from KThread import *
from chaosmonkey import CMServer


class LogMod(Enum):
    ADDITION = 1
    APPEND = 2
    REPLACEMENT = 3
    DELETION = 4


class KVServer(kvstore_pb2_grpc.KeyValueStoreServicer):
    follower = 0
    candidate = 1
    leader = 2

    def __init__(self, addresses: list, id: int, server_config: dict):
        ### Persistent state on all servers, update on stable storage before responding to RPCs
        self.currentTerm = 0
        self.votedFor = -1
        self.log = []  # first index is 1

        # load persistent state from json file
        self.id = id
        self.persistent_file = '/data/config-%d' % self.id
        self.diskLog = "/data/log-%d.pkl" % self.id
        self.diskStateMachine = "/data/state_machine-%d.pkl" % self.id
        # Todo: will re-enable load later
        # self.load()
        self.stateMachine = {}  # used to be storage

        # Config
        self.requestTimeout = server_config["request_timeout"]  # in ms
        self.maxElectionTimeout = server_config["election_timeout"]
        self.keySizeLimit = server_config["key_size"]
        self.valSizeLimit = server_config["value_size"]

        ### Volatile state on all servers
        self.commitIndex = -1  # known to be commited, init to 0
        # if larger than lastApplied, apply log to state machine
        self.lastApplied = -1  # index of highest log entry applied to state machine, init to 0
        self.role = KVServer.follower
        self.leaderID = -1
        self.peers = []
        self.lastUpdate = time.time()

        self.appendEntriesCond = Condition()
        self.appliedStateMachCond = Condition()
        self.roleCond = Condition()

        # current state
        self.currElectionTimeout = float(random.randint(self.maxElectionTimeout / 2, self.maxElectionTimeout) / 1000)  # in sec
        for idx, addr in enumerate(addresses):
            if idx != self.id:
                self.peers.append(idx)
        self.majority = int(len(addresses) / 2) + 1
        self.lastLogIndex = -1
        self.lastLogTerm = 0
        self.addresses = addresses  # number of nodes implied here
        self.cmserver = CMServer(num_server=len(addresses))

        # logging setting
        logging.basicConfig(filename='/data/logger-%d.txt' % self.id,
                            level=logging.NOTSET,
                            filemode='a',
                            format='%(asctime)s,%(msecs)d %(levelname)s %(message)s',
                            datefmt='%H:%M:%S')
        self.logger = logging.getLogger('raft')
        self.logger.setLevel(logging.NOTSET)
        self.logger.info(f'RAFT[Chaos]: Initial ChaosMonkey matrix: \n<{self.cmserver}>')

        ### Volatile state on leaders
        self.nextIndex = [0] * len(addresses)  # index of next log entry to send to that server
        self.matchIndex = [-1] * len(addresses)  # highest log entry known to be replicated
        # if there exists such N that N> commitIndex and majority of matchIndex[i] >= N
        # and log[N].term ==currentTerm, set commitIndex = N
        self.numVotes = 0

        # Todo: for debugging only
        self.debug1 = 0

    def load(self):
        if os.path.isfile(self.persistent_file):
            with open(self.persistent_file, 'r') as f:
                data_store = json.load(f)
                self.currentTerm = data_store["currentTerm"]
                self.votedFor = data_store["votedFor"]

    # Todo: check if all currentTerm and votedFor has .save() save persistent state to json file
    def save(self, current_term = -1, voted_for = -1):
        if current_term != -1:
            self.currentTerm = current_term
        if voted_for != -1:
            self.votedFor = voted_for
        persistent = {"currentTerm": self.currentTerm, "votedFor": self.votedFor}
        with open(self.persistent_file, 'w') as f:
            json.dump(persistent, f)

    # Leader or Candidate steps down to follower
    def step_down(self):
        if self.role == KVServer.candidate:
            self.election.kill()
            self.lastUpdate = time.time()
            self.role = KVServer.follower
        elif self.role == KVServer.leader:
            self.logger.critical("Raft[Role]: Candidate step down when higher term")
            self.leader_state.kill()
            self.follower_state = KThread(target=self.follower, args=())
            self.follower_state.start()

    def follower(self):
        self.logger.critical(f'RAFT[Role]: Running as a follower')
        self.role = KVServer.follower
        self.lastUpdate = time.time()
        while time.time() - self.lastUpdate <= self.currElectionTimeout:
            pass
        self.start_election()
        while True:
            self.lastUpdate = time.time()
            self.currElectionTimeout = float(random.randint(self.maxElectionTimeout / 2, self.maxElectionTimeout) / 1000)
            while time.time() - self.lastUpdate <= self.currElectionTimeout:
                pass
            # kill old election thread
            if self.election.is_alive():
                self.election.kill()
            self.start_election()

    def start_election(self):
        # Create a new thread for leader election
        self.logger.info("RAFT[Role]: Start leader election")
        self.role = KVServer.candidate
        self.save(current_term=self.currentTerm+1, voted_for=self.id)
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

    def requestVote(self, request, context):
        req_term = request.term
        req_candidate_id = request.candidateID
        req_last_log_ind = request.lastLogIndex
        req_last_log_term = request.lastLogTerm
        print(f'Receive request vote from <{req_candidate_id}>')
        vote_granted = True
        # Todo: not sure if req_last_log_term < self.lastLogTerm is needed
        if req_term < self.currentTerm or req_last_log_ind < self.lastLogIndex or \
                req_last_log_term < self.lastLogTerm or \
                (self.votedFor != -1 and self.votedFor != req_candidate_id):
            vote_granted = False
            self.logger.debug(f'RAFT[Vote]: vote denied for server <{req_candidate_id}>')
        if req_term == self.currentTerm:
            self.save(voted_for=req_candidate_id) # TODO: Add lock here?
            self.logger.debug(f'RAFT[Vote]: vote granted for <{req_candidate_id}>')
        # Find higher term in RequestVote message
        else:
            self.logger.critical(f'RAFT[Vote]: Stepping down since server <{req_candidate_id}> has higher term')
            self.save(current_term=req_term, voted_for=req_candidate_id)
            step_down_kth = KThread(target=self.step_down, args=())
            step_down_kth.start()
        return kvstore_pb2.VoteResponse(term=self.currentTerm, voteGranted=vote_granted)

    # Todo: Add chaos monkey?
    def thread_election(self, idx, addr):
        vote_request = kvstore_pb2.VoteRequest(term=self.currentTerm, candidateID=self.id,
                                               lastLogIndex=self.lastLogIndex, lastLogTerm=self.lastLogTerm)
        try:
            with grpc.insecure_channel(addr) as channel:
                stub = kvstore_pb2_grpc.KeyValueStoreStub(channel)
                self.logger.debug(f'Send vote request to server: <{idx}>')
                req_vote_resp = stub.requestVote(
                    vote_request, timeout=self.requestTimeout)  # timeout keyword ok?
                # print(req_vote_resp.voteGranted, req_vote_resp.term)
                # if I receive voteGranted
                # TODO: Add lock here to consider concurrency
                if req_vote_resp.voteGranted:
                    self.logger.debug(f'vote received from server <{idx}>, majority is: <{self.majority}>')
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
                    self.logger.debug(f'RAFT[Vote] vote rejected from server: <{idx}>')
                    # discover higher term
                    if req_vote_resp.term > self.currentTerm:
                        self.save(current_term=req_vote_resp.term)
                        self.step_down()
        except Exception as e:
            self.logger.error(e)

    def leader(self):
        self.logger.critical(f'RAFT[Role]: Running as a leader')
        self.role = KVServer.leader
        # for each server it's the index of next log entry to send to that server
        # init to leader last log index + 1
        self.nextIndex = [self.lastLogIndex + 1] * len(self.addresses)
        # for each server, index of highest log entry known to be replicated on server
        # init to 0, increase monotonically
        self.matchIndex = [0] * len(self.addresses)
        self.append_entries()

    # Leader sends append_entry message as log replication and heart beat
    def append_entries(self):
        while True:
            # Todo: for debugging only
            self.debug1 += 1
            self.logModify([self.debug1, "aa", "bb"], LogMod.APPEND)
            self.logModify([self.debug1, "bb", "cc"], LogMod.APPEND)
            for idx, addr in enumerate(self.addresses):
                if idx == self.id:
                    continue
                # Create a thread for each append_entry message
                append_thread = KThread(target=self.thread_append_entry, args=(idx, addr,))
                append_thread.start()
            # Send append entry every following seconds
            # Todo: will release during wait
            self.appendEntriesCond.acquire()
            self.appendEntriesCond.wait(timeout=0.5)
            self.appendEntriesCond.release()

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
                stub = kvstore_pb2_grpc.KeyValueStoreStub(channel)
                if random.uniform(0, 1) < self.cmserver.fail_mat[self.leaderID][self.id]:
                    print("Chaos Monkey blocking")
                    self.logger.warning(f'RAFT[ABORTED]: we will not receive from <{self.leaderID}> '
                                        f'because of ChaosMonkey')
                else:
                    self.logger.debug(f'RAFT: Send append_entry to <{idx}>')
                    append_entry_response = stub.appendEntries(
                        append_request, timeout = self.requestTimeout)
                    if not append_entry_response.success:
                        self.logger.debug("RAFT: thread_append_entry failed")
                        # Failed since another server is leader now
                        if append_entry_response.term > self.currentTerm:
                            self.save(current_term=append_entry_response.term)
                            self.step_down()
                        # Failed because of log inconsistency, decrement nextIndex and retry
                        else:
                            self.nextIndex[idx] = max(self.nextIndex[idx] - 1, 0)  # Todo: how to decrement correctly
                    # Success
                    else:
                        self.logger.debug("RAFT: thread_append_entry success")
                        self.matchIndex[idx] = last_req_log_idx
                        n_list = sorted(self.matchIndex)
                        # TODO: write to disk upon majority
                        # if there exists such N that N> commitIndex and majority of matchIndex[i] >= N
                        # and log[N].term ==currentTerm, set commitIndex = N
                        N = n_list[int(len(n_list) / 2)]
                        if N >= 0 and N > self.commitIndex and self.log[N][0] == self.currentTerm:
                            self.commitIndex = N
                            self.logger.debug(f"RAFT: Commit index on leader updates to: {N}")
                            disk_write_kth = KThread(target=self.applyToStateMachine, args=(self.lastApplied,))
                            disk_write_kth.start()
        except Exception as e:
            self.logger.error(e)

    def appendEntries(self, request, context):  # receiving/server side
        # int32 term = 1;
        # int32 leaderID = 2;
        # int32 prevLogIndex = 3;
        # int32 prevLogTerm = 4;
        # repeated LogEntry entries = 5;
        # int32 leaderCommit = 6;
        inc_server_id = request.leaderID
        if random.uniform(0, 1) < self.cmserver.fail_mat[inc_server_id][self.id]:
            self.logger.warning(f'RAFT[ABORTED]: append entries from server <{inc_server_id}> '
                                f'to <{self.id}>, because of ChaosMonkey')
        else:
            success = False
            try:
                # self.logger.info("Received appendEntries")
                self.lastUpdate = time.time()
                tmp_entries = []
                for row in request.entries:
                    r = [row.term, row.key, row.val]
                    tmp_entries.append(r)
                    # self.logger.info(f'row: <{r}>')
                # reply false if term < currentTerm,
                # or log doesn't log doesn't contain an entry at prevLogIndex whose term matches prevLogTerm
                if request.term < self.currentTerm or request.prevLogIndex > len(self.log) \
                        or (request.prevLogIndex < len(self.log) and
                            self.log[request.prevLogIndex][0] != request.prevLogTerm):
                    if request.term < self.currentTerm:  # Todo: do we need to start election here?
                        election_kth = KThread(target=self.step_down, args=())
                        election_kth.start()
                    self.logger.warning(f'RAFT: appendEntries received on server <{self.id}>, will return false; ')
                    self.logger.debug(f'Parameters for false: req term: <{request.term}>, cur term: '
                                      f'<{self.currentTerm}>, req prevLogIdx: <{request.prevLogIndex}>, '
                                      f'length of server log <{len(self.log)}>')
                    if request.prevLogIndex < len(self.log):
                        self.logger.debug(f'term of log on prev log index: <{self.log[request.prevLogIndex][0]}>'
                                          f'request prev log term: <{request.prevLogTerm}>')
                else:
                    self.save(current_term=max(self.currentTerm, request.term))
                    # self.logger.info("RAFT: AppendEntries should succeed unless there is conflict entries")
                    success = True
                    #     existing entry conflicts with a new one, same idx different terms,
                    #     delete the existing entry and all that follow it
                    # self.logger.info(f'RAFT: checking conflicting entries')
                    itr = 0
                    if len(self.log) > 0:
                        for a, b in zip(tmp_entries, self.log[request.prevLogIndex:]):
                            if a != b:
                                self.logger.warning(f'RAFT[Log]: Found conflict at index: '
                                                    f'<{request.prevLogIndex + itr}>')
                                self.logModify(request.prevLogIndex + itr, LogMod.DELETION)
                            itr += 1
                    # Heartbeat
                    if len(tmp_entries) == 0:
                        self.logger.debug("RAFT: received a heartbeat")
                        pass
                    # Normal append entries
                    else:
                        # Append any new entries not already in the log
                        to_append_length = request.prevLogIndex + len(tmp_entries) - len(self.log)
                        # self.logger.debug(f'RAFT: length of log to append: <{to_append_length}>')
                        if to_append_length > 0:
                            self.logModify(tmp_entries[-to_append_length:], LogMod.ADDITION)
                        # If leaderCommit > commitIndex, set commitIndex = min(leaderCommit, index of last new entry)
                        # print("Received log from appendEntries is: ", tmp_entries)
                        self.logger.debug(f'RAFT: Checking if we need to write to disk: <{request.leaderCommit}>,'
                                          f'<{self.commitIndex}>, <{self.lastLogIndex}>')
                        if request.leaderCommit > self.lastApplied:
                            self.commitIndex = min(request.leaderCommit, self.lastLogIndex)
                            app_state_mach_kth = KThread(target=self.applyToStateMachine, args=(self.lastApplied,))
                            app_state_mach_kth.start()
                    # int32 term = 1;
                    # bool success = 2;
            except Exception as e:
                self.logger.error(e)
            return kvstore_pb2.AppendResponse(term=self.currentTerm, success=success)

    # Todo: always use this to update log
    def logModify(self, para, operation: LogMod):
        # self.logger.debug(f'RAFT[Log]: Log modify: <{para}>, '
        #                   f'operation: <{operation}>')
        if operation == LogMod.ADDITION:
            self.log += para
        elif operation == LogMod.APPEND:
            self.log.append(para)
        elif operation == LogMod.REPLACEMENT:
            self.log = para
        elif operation == LogMod.DELETION:
            self.log = self.log[:para]
        self.lastLogIndex = len(self.log) - 1
        self.lastLogTerm = self.log[self.lastLogIndex][0]
        with open(self.diskLog, 'wb') as f:
            pkl.dump(self.log, f)
        #     Todo: not needed when it's the leader, what about follower?
        if self.lastLogTerm > self.currentTerm:
            self.save(current_term=self.lastLogTerm)
        self.logger.debug(f'RAFT[Log]: Log updated on disk of server <{self.id}> ,'
                          f'last log index now: <{self.lastLogIndex}>'
                          f'log is: <{self.log}>')

    def applyToStateMachine(self, last_applied):
        # TODO: maybe we can append only? maybe we need synchronization
        to_update = self.log[last_applied + 1:self.commitIndex + 1]
        for row in to_update:
            self.stateMachine[row[1]] = row[2]
        with open(self.diskStateMachine, 'wb') as f:
            pkl.dump(self.stateMachine, f)
        self.lastApplied = self.commitIndex
        self.logger.debug(f'RAFT[StateMach]: Last applied index: <{self.lastApplied}>, '
                          f'state machine updated to: <{self.stateMachine}>')

    # def readWithKey(self, key):
    #     n = len(self.log)
    #     for i in range(n - 1, -1, -1):
    #         if self.log[i][1] == key: return self.log[i][2]
    #     return ""

    def run(self):
        # Create a thread to run as follower
        self.follower_state = KThread(target=self.follower, args=())
        self.follower_state.start()

    # Checkpoint 1 Get Put Methods
    # Todo: no longer needed?
    # def localGet(self, key):
    #     '''
    #     val = self.readWithKey(key)
    #     if val == "": return kvstore_pb2.GetResponse(ret = kvstore_pb2.FAILURE, value = val)
    #     else: return kvstore_pb2.GetResponse(ret = kvstore_pb2.SUCCESS, value = val)
    #     '''
    #     resp = kvstore_pb2.GetResponse()
    #     try:
    #         resp.value = self.stateMachine[key]
    #         resp.ret = kvstore_pb2.SUCCESS
    #         self.logger.info(f'RAFT[KVStore]: localGet <{key}, {resp.value}>')
    #     except KeyError:
    #         resp.ret = kvstore_pb2.FAILURE
    #         self.logger.warning(f'RAFT[KVStore]: localGet failed, no such key: [{key}]')
    #     return resp

    # Todo: no longer needed?
    # def localPut(self, key, val):
    #     resp = kvstore_pb2.PutResponse()
    #     self.stateMachine[key] = val  # dictionary
    #     resp.ret = kvstore_pb2.SUCCESS
    #     self.logger.info(f'RAFT[KVStore]: localPut <{key}, {val}>')
    #     return resp

    # Todo: add client ID and sequence number
    def Get(self, request, context):
        # string key = 1;
        # int32 serverID = 2;
        if self.role == KVServer.candidate:
            self.logger.warning(f'RAFT[KVStore]: Server get encountered election process')
            self.roleCond.acquire()
            self.roleCond.wait_for(lambda: (self.role != KVServer.candidate), timeout=self.requestTimeout)
            self.roleCond.release()
        if self.role == KVServer.leader:
            if random.uniform(0, 1) < self.cmserver.fail_mat[request.serverID][self.id]:
                self.logger.warning(f'RAFT[ABORTED]: Server get redirect failed from server <{request.serverID}>, '
                                    f'to leader <{self.id}>, because of ChaosMonkey')
            else:
                try:
                    self.logger.info(f'RAFT[KVStore]: localGet <{request.key}, {self.stateMachine[request.key]}>')
                    context.set_code(grpc.StatusCode.OK)
                    # string value = 1;
                    # ReturnCode ret = 2;
                    # int32 leaderID = 3;
                    return kvstore_pb2.GetResponse(value=self.stateMachine[request.key], ret=kvstore_pb2.SUCCESS,
                                                   leaderHint=self.id)
                except KeyError:
                    self.logger.warning(f'RAFT[KVStore]: localGet failed, no such key: [{request.key}]')
                    context.set_code(grpc.StatusCode.CANCELLED)
                    return kvstore_pb2.GetResponse(value="", ret=kvstore_pb2.FAILURE, leaderHint=self.id)
        elif self.role == KVServer.follower:  # Role is follower

            with grpc.insecure_channel(self.addresses[self.leaderID]) as channel:
                try:
                    stub = kvstore_pb2_grpc.KeyValueStoreStub(channel)
                    get_response = stub.Get(kvstore_pb2.GetRequest(key=request.key,
                                                                   serverID=self.id), timeout=self.requestTimeout)
                    if get_response.ret == kvstore_pb2.SUCCESS:
                        self.logger.info(f'RAFT[KVStore]: Server get redirect success from server <{request.serverID}>, '
                                         f'to leader <{self.id}>')
                        context.set_code(grpc.StatusCode.OK)
                        return kvstore_pb2.GetResponse(value=get_response.value, ret=kvstore_pb2.SUCCESS,
                                                       leaderHint=self.id)
                    else:
                        self.logger.warning(f'RAFT[KVStore]: Server get redirect failed from server '
                                            f'<{request.serverID}>, '
                                            f'to leader <{self.id}>')
                        context.set_code(grpc.StatusCode.CANCELLED)
                        return kvstore_pb2.GetResponse(value="", ret=kvstore_pb2.FAILURE, leaderHint=self.id)
                except Exception as e:
                    self.logger.error(e)
        else:
            self.logger.warning(f'RAFT[KVStore]: Server get timeout due to long election')
            context.set_code(grpc.StatusCode.CANCELLED)
            return kvstore_pb2.GetResponse(value="", ret=kvstore_pb2.FAILURE, leaderHint=self.leaderID)

    # Todo: add client ID and sequence number
    def Put(self, request, context):
        # string key = 1;
        # string value = 2;
        # int32 clientID = 4;
        # int32 sequenceNum = 5;
        # if command received from client: append entry to local log, respond after entry applied to state machine
        if self.role == KVServer.leader:
            if random.uniform(0, 1) < self.cmserver.fail_mat[request.serverID][self.id]:
                self.logger.warning(f'RAFT[ABORTED]: Server put redirect failed from server <{request.serverID}>, '
                                    f'to leader <{self.id}>, because of ChaosMonkey')
            else:
                # Todo: current term correct?
                self.logModify([[self.currentTerm, request.key, request.value]], LogMod.ADDITION)
                put_log_ind = self.lastLogIndex
                self.appendEntriesCond.acquire()
                self.appendEntriesCond.notify()
                self.appendEntriesCond.release()
                self.appliedStateMachCond.acquire()
                self.appliedStateMachCond.wait_for(lambda: (self.lastApplied >= put_log_ind),
                                                   timeout=self.requestTimeout)
                self.appliedStateMachCond.release()
                # ReturnCode ret = 1;
                # int32 leaderID = 2;
                if self.lastApplied >= put_log_ind:
                    self.logger.info(f'RAFT[KVStore]: Server put success on leader <{self.id}>')
                    context.set_code(grpc.StatusCode.OK)  # Todo: why is this needed?
                    return kvstore_pb2.PutResponse(ret=kvstore_pb2.OK2CLIENT, leaderHint=self.id)
                else:
                    self.logger.warning(f'RAFT[KVStore]: Server put error (timeout?) on leader <{self.id}>')
                    context.set_code(grpc.StatusCode.CANCELLED)
                    return kvstore_pb2.PutResponse(ret=kvstore_pb2.ERROR2CLIENT, leaderHint=self.id)
        else:
            return kvstore_pb2.PutResponse(ret=kvstore_pb2.NOT_LEADER, leaderHint=self.leaderID)



    def registerClient(self, request, context):


    def clientRequest(self, request, context):
        pass

    def clientQuery(self, request, context):
        pass
    # Async IO implementation
    # def Get(self, request, context):
    #     # Asyncio implementation
    #     # https://github.com/grpc/grpc/issues/16329
    #     def getProcessResponse(append_resp):
    #         if append_resp.ret == kvstore_pb2.SUCCESS:
    #             resp = kvstore_pb2.GetResponse(ret=kvstore_pb2.SUCCESS,
    #                                            value=append_resp.value)
    #             context.set_code(grpc.StatusCode.OK)
    #             return resp
    #     key = request.key
    #     resp = self.localGet(key)
    #     for idx, addr in enumerate(self.addresses):
    #         if idx == self.id:
    #             continue
    #         self.logger.info(f'RAFT: serverGet from {addr}')
    #         with grpc.insecure_channel(addr) as channel:
    #             # Asyncio implementation
    #             # stub = kvstore_pb2_grpc.KeyValueStoreStub(channel)
    #             # append_resp = stub.appendEntries.future(kvstore_pb2.AppendRequest(type=kvstore_pb2.GET, key=key))
    #             # append_resp.add_done_callback(getProcessResponse)
    #             stub = kvstore_pb2_grpc.KeyValueStoreStub(channel)
    #             append_resp = stub.appendEntries(kvstore_pb2.AppendRequest(
    #                 type=kvstore_pb2.GET, key=key), timeout = self.requestTimeout) # timeout?
    #             if append_resp.ret == kvstore_pb2.SUCCESS:
    #                 resp = kvstore_pb2.GetResponse(ret=kvstore_pb2.SUCCESS,
    #                                                value=append_resp.value)
    #                 context.set_code(grpc.StatusCode.OK)
    #                 return resp
    #             else: context.set_code(grpc.StatusCode.CANCELLED)
    #     return kvstore_pb2.GetRequest(ret=kvstore_pb2.FAILURE)


