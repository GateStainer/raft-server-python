import grpc
import kvstore_pb2
import kvstore_pb2_grpc
import random
import logging
import json
import time
import os
import sys
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
        self.persistent_file = 'log/config-%d' % self.id
        self.diskLog = "log/log-%d.pkl" % self.id
        # self.loggerFile = "log/log-%d.txt" % self.id
        self.diskStateMachine = "log/state_machine-%d.pkl" % self.id
        # Todo: will re-enable load later
        # self.load()
        self.stateMachine = {}  # used to be storage

        # Config
        self.requestTimeout = server_config["request_timeout"]  # in ms
        self.maxElectionTimeout = server_config["election_timeout"]
        self.keySizeLimit = server_config["key_size"]
        self.valSizeLimit = server_config["value_size"]
        self.appendEntriesTimeout = float(server_config["app_entries_timeout"])/1000

        ### Volatile state on all servers
        self.commitIndex = -1  # known to be commited, init to 0
        # if larger than lastApplied, apply log to state machine
        self.lastApplied = -1  # index of highest log entry applied to state machine, init to 0


        self.role = KVServer.candidate
        self.leaderID = -1
        self.peers = []
        self.lastUpdate = time.time()

        # Condition variables
        self.appendEntriesCond = Condition()
        self.appliedStateMachCond = Condition()
        self.lastCommittedTermCond = Condition()
        self.leaderCond = Condition()
        self.candidateCond = Condition()
        self.followerCond = Condition()

        # Client related
        self.registeredClients = []
        self.clientReqResults = {}  # clientID: [stateMachineOutput, sequenceNum]

        # current state
        self.currElectionTimeout = random.uniform(self.maxElectionTimeout / 2, self.maxElectionTimeout) / 1000  # in sec
        for idx, addr in enumerate(addresses):
            if idx != self.id:
                self.peers.append(idx)
        self.majority = int(len(addresses) / 2) + 1
        self.lastLogIndex = -1
        self.lastLogTerm = 0
        self.addresses = addresses  # number of nodes implied here
        self.cmserver = CMServer(num_server=len(addresses))

        # create logger with 'raft'
        self.logger = logging.getLogger('raft')
        self.logger.setLevel(logging.DEBUG)
        # create formatter and add it to the handlers
        formatter = logging.Formatter('[%(asctime)s,%(msecs)d %(levelname)s]: %(message)s',
                                      datefmt='%M:%S')
        # create file handler which logs even debug messages
        os.makedirs(os.path.dirname('log/logger-%d.txt' % self.id), exist_ok=True)
        fh = logging.FileHandler('log/logger-%d.txt' % self.id)
        fh.setLevel(logging.INFO)
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)
        # create console handler with a higher log level
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)

        # # Last version logging setting
        # logging.basicConfig(filename='log/logger-%d.txt' % self.id,
        #                     filemode='a',
        #                     format='%(asctime)s,%(msecs)d %(levelname)s %(message)s',
        #                     datefmt='%H:%M:%S')
        # self.logger = logging.getLogger('raft')
        # self.logger.setLevel(logging.NOTSET)
        self.logger.debug(f'[Chaos]: Initial ChaosMonkey matrix: \n<{self.cmserver}>')

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
    def save(self, current_term, voted_for):
        self.currentTerm = current_term
        self.votedFor = voted_for
        persistent = {"currentTerm": self.currentTerm, "votedFor": self.votedFor}
        with open(self.persistent_file, 'w') as f:
            json.dump(persistent, f)

    def follower(self):
        while True:
            # self.role = KVServer.follower  # Todo: is this correct
            self.logger.critical(f'[Role]: Running as a follower, elec timeout <%.4f>' % self.currElectionTimeout)
            self.save(current_term=self.currentTerm, voted_for=-1)
            self.lastUpdate = time.time()
            while time.time() - self.lastUpdate <= self.currElectionTimeout:
                with self.followerCond:
                    self.followerCond.wait(self.currElectionTimeout - (time.time() - self.lastUpdate))  # -elapsed time
            # self.logger.debug(f'Current time <{time.time()}>, last update <{self.lastUpdate}>, deduct to '
            #                   f'<{time.time() - self.lastUpdate}>election timeout <{self.currElectionTimeout}>')
            self.role = KVServer.candidate  # Todo: change to candidate here?
            with self.candidateCond:
                self.candidateCond.notify_all()
            with self.followerCond:
                self.followerCond.wait()

    def candidate(self):
        with self.candidateCond:
            self.candidateCond.wait()
        while True:
            self.logger.critical(f'[Role]: Running as a candidate, elec timeout <%.4f>' % self.currElectionTimeout)
            # Upon conversion to candidate, start election
            # Increment current term, vote for self, reset election timer, send requestVote RPCs to all other servers

            # self.logger.critical(f'RAFT[Vote]: Server <{self.id}> initiated voting for term <{self.currentTerm}> '
            #                      f'took <%.4f> seconds' % (time.time()-start_time))
            self.save(current_term=self.currentTerm+1, voted_for=self.id)
            self.numVotes = 1
            self.currElectionTimeout = random.uniform(self.maxElectionTimeout / 2, self.maxElectionTimeout) / 1000
            self.election = KThread(target=self.initiateVote, args=())
            self.election.start()
            self.logger.info(f'[Vote]: Start, voted for self <{self.id}> term <{self.currentTerm}> '
                             f'election timeout: <%.4f>' % self.currElectionTimeout)
            self.lastUpdate = time.time()
            while time.time() - self.lastUpdate <= self.currElectionTimeout and self.role == KVServer.candidate:
                with self.candidateCond:
                    self.candidateCond.wait(self.currElectionTimeout-(time.time() - self.lastUpdate))  # - elapse time
                if self.numVotes >= self.majority or self.role == KVServer.follower:
                    break
            self.save(current_term=self.currentTerm, voted_for=-1)
            if self.role == KVServer.leader:
                with self.leaderCond:
                    self.leaderCond.notify_all()
                with self.candidateCond:
                    # self.logger.critical(f"in candidate, larger than majority")
                    self.candidateCond.wait()
            elif self.role == KVServer.follower:
                with self.followerCond:
                    self.followerCond.notify_all()
                with self.candidateCond:
                    self.candidateCond.wait()
            # Todo: is this needed?
            # self.lastUpdate = time.time()
            # if time.time() - self.lastUpdate <= self.currElectionTimeout:
            #     with self.candidateCond:
            #         self.candidateCond.wait(self.currElectionTimeout-(time.time() - self.lastUpdate))

    def leader(self):
        while True:
            # mcip: Use condition to control instead
            with self.leaderCond:
                # self.logger.critical(f"reached leader111, larger than majority")
                self.leaderCond.wait()
            if self.role == KVServer.follower:
                with self.followerCond:
                    self.followerCond.notify_all()
                with self.leaderCond:
                    self.leaderCond.wait()
            elif self.role == KVServer.candidate:
                with self.candidateCond:
                    self.candidateCond.notify_all()
                with self.leaderCond:
                    self.leaderCond.wait()

            # self.role = KVServer.leader  # Todo: is this correct?
            self.logger.critical(f'[Role]: Running as a leader')
            self.save(current_term=self.currentTerm, voted_for=-1)
            self.leaderID = self.id
            # for each server it's the index of next log entry to send to that server
            # init to leader last log index + 1
            self.nextIndex = [self.lastLogIndex + 1] * len(self.addresses)
            # for each server, index of highest log entry known to be replicated on server
            # init to 0, increase monotonically
            self.matchIndex = [0] * len(self.addresses)
            # Todo: might need debugging?
            # Upon becoming leader, append no-op entry to log (6.4)
            self.logModify([self.currentTerm, f"no-op: leader-{self.id}", "no-op"], LogMod.APPEND)
            self.append_entries()

    def initiateVote(self):
        # Todo: mcip, make sure the term is the same while request vote????
        req_term = self.currentTerm
        for idx, addr in enumerate(self.addresses):
            if idx == self.id:
                continue
            # Create a thread for each request vote
            election_thread = KThread(target=self.thread_election, args=(idx, addr, req_term, ))
            election_thread.start()

    # Todo: All servers: If RPC request or response contains term T> currentTerm, set current term = T,
    #  convert to follower
    def convToFollowerIfHigherTerm(self, term, voted_for):
        if term > self.currentTerm:
            if self.role == KVServer.candidate:
                self.save(current_term=term, voted_for=voted_for)
                self.role = KVServer.follower
                with self.candidateCond:
                    self.candidateCond.notify_all()
            elif self.role == KVServer.leader:  # leader
                self.save(current_term=term, voted_for=voted_for)
                self.role = KVServer.follower
                with self.leaderCond:
                    self.leaderCond.notify_all()

    # Todo: Add chaos monkey?
    def thread_election(self, idx, addr, req_term):
        try:
            # Todo: shouldn't always increment term here ???
            vote_request = kvstore_pb2.VoteRequest(term=self.currentTerm, candidateID=self.id,
                                                   lastLogIndex=self.lastLogIndex, lastLogTerm=req_term)
            # with grpc.insecure_channel(addr) as channel:
            channel = grpc.insecure_channel(addr)
            grpc.channel_ready_future(channel).result()
            stub = kvstore_pb2_grpc.KeyValueStoreStub(channel)
            # self.logger.debug(f'Send vote request to server: <{idx}>')
            req_vote_resp = stub.requestVote(vote_request, timeout=self.requestTimeout)  # timeout keyword ok?
            # Todo: mcip, does this improve?
            num_rej_votes = 0
            # Todo: Add lock here to consider concurrency
            if req_vote_resp.voteGranted:
                self.logger.info(f'[Vote]: received from <{idx}>, vote count: <{self.numVotes}>')
                if self.role == KVServer.candidate:
                    self.numVotes += 1
                    if self.numVotes >= self.majority:
                        self.role = KVServer.leader
                        with self.candidateCond:
                            # self.logger.critical(f"thread_election, larger than majority")
                            self.candidateCond.notify_all()
            else:
                self.logger.info(f'[Vote]: rejected from <{idx}> its term: {req_vote_resp.term}')
                # Todo: added by mcip, does this actually improve?
                num_rej_votes += 1
                if self.role == KVServer.follower and req_vote_resp.term > self.currentTerm:
                    self.save(current_term=req_vote_resp.term, voted_for=-1)
                # Todo: All servers: If RPC request or response contains term T> currentTerm, set current term = T,
                #  convert to follower
                self.convToFollowerIfHigherTerm(req_vote_resp.term, voted_for=-1)
                    # self.role = KVServer.follower
                    # with self.candidateCond:
                    #     self.candidateCond.notify_all()
                # elif num_rej_votes > self.majority:
                #     self.save(current_term=self.currentTerm, votedFor=-1)
        except Exception as e:
            self.logger.error("[Vote]: f() thread_election:")
            self.logger.error(e)

    def requestVote(self, request, context):  # Receiving vote request and process
        # Todo: not needed?
        # self.lastUpdate = time.time()
        try:
            req_term = request.term
            req_candidate_id = request.candidateID
            req_last_log_ind = request.lastLogIndex
            req_last_log_term = request.lastLogTerm
            # self.logger.debug(f'RAFT[Vote]: Receive request vote from <{req_candidate_id}>')
            vote_granted = True
            # Todo: not sure if req_last_log_term < self.lastLogTerm is needed
            # Reply false if term < currentTerm
            # If votedFor is null/candidateID, and candidate's log is at least as updated as receiver's log, grant vote
            if req_term < self.currentTerm or req_last_log_ind < self.lastLogIndex or \
                    req_last_log_term < self.lastLogTerm or \
                    (self.votedFor != -1 and self.votedFor != req_candidate_id):
                vote_granted = False
                self.logger.info(f'[Vote]: reject vote request from <{req_candidate_id}>, '
                                 f'currentTerm <{self.currentTerm}>'
                                 f'\n reason: <{req_term < self.currentTerm}>, <{req_last_log_ind < self.lastLogIndex}>'
                                 f', <{req_last_log_term < self.lastLogTerm}> or voted for another')
                if self.role == KVServer.follower and req_term > self.currentTerm:
                    self.save(current_term=req_term, voted_for=-1)
                # Todo: All servers: If RPC request or response contains term T> currentTerm, set current term = T,
                #  convert to follower
                self.convToFollowerIfHigherTerm(req_term, voted_for=req_candidate_id)
            elif req_term == self.currentTerm:
                self.lastUpdate = time.time()
                self.save(current_term=self.currentTerm, voted_for=req_candidate_id)  # TODO: Add lock here?
                self.logger.info(f'[Vote]: vote granted for <{req_candidate_id}> w term <{self.currentTerm}>')
            # Find higher term in RequestVote message
            elif req_term > self.currentTerm:
                self.lastUpdate = time.time()
                if self.role == KVServer.follower:
                    self.save(current_term=req_term, voted_for=req_candidate_id)
                # Todo: All servers: If RPC request or response contains term T> currentTerm, set current term = T,
                #  convert to follower
                self.convToFollowerIfHigherTerm(req_term, voted_for=req_candidate_id)
                self.logger.critical(f'[Vote]: vote granted for <{req_candidate_id}> '
                                     f'due to higher term <{req_term}>')
            # Todo: mcip: if granting the vote to someone, should set back the lastUpdate time?
            return kvstore_pb2.VoteResponse(term=self.currentTerm, voteGranted=vote_granted)
        except Exception as e:
            self.logger.error("[Vote]: f() requestVote:")
            self.logger.error(e)

    # Leader sends append_entry message as log replication and heart beat
    def append_entries(self):
        while self.role == KVServer.leader:
            # Todo: for debugging only
            # # self.debug1 += 1
            # self.logModify([self.debug1, "aa", "bb"], LogMod.APPEND)
            # self.logModify([self.debug1, "bb", "cc"], LogMod.APPEND)
            app_ent_term = self.currentTerm
            for idx, addr in enumerate(self.addresses):
                if idx == self.id:
                    continue
                # Create a thread for each append_entry message
                append_thread = KThread(target=self.thread_append_entry, args=(idx, addr, app_ent_term,))
                append_thread.start()
            # Send append entry every following seconds, or be notified and wake up
            # Todo: will release during wait
            with self.appendEntriesCond:
                self.appendEntriesCond.wait(timeout=self.appendEntriesTimeout)

    def thread_append_entry(self, idx, addr, app_ent_term):
        try:
            append_request = kvstore_pb2.AppendRequest()
            append_request.term = app_ent_term  # int32 term = 1;
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
            self.nextIndex[idx] = self.lastLogIndex + 1  # Todo: should inc to +1 here?
            # with grpc.insecure_channel(addr) as channel:
            channel = grpc.insecure_channel(addr)
            grpc.channel_ready_future(channel).result()
            # int32 term = 1;
            # bool success = 2;
            stub = kvstore_pb2_grpc.KeyValueStoreStub(channel)
            if random.uniform(0, 1) < self.cmserver.fail_mat[self.leaderID][self.id]:
                self.logger.warning(f'[ABORTED]: we will not receive from <{self.leaderID}> '
                                    f'because of ChaosMonkey')
            else:
                self.logger.info(f'[AP_En]: thread_append_entry to <{idx}>, '
                                 f'req last log <{last_req_log_idx}>')
                                 # f'req entries \n<{append_request.entries}>')
                append_entry_response = stub.appendEntries(
                    append_request, timeout=self.requestTimeout)
                if not append_entry_response.success:
                    self.logger.info(f"[AP_En]: thread_append_entry to <{idx}> failed, "
                                     f"its term <{append_entry_response.term}>, leader's <{self.currentTerm}>")
                    # Failed because of log inconsistency, decrement nextIndex and retry
                    if append_entry_response.term <= self.currentTerm:
                        self.logger.info(f"[AP_En]: log inconsistency, nextIndex for <{idx}> dec from "
                                         f"<{self.nextIndex[idx]}> to <{max(append_request.prevLogIndex - 1, 0) }>")
                        # Todo: how to decrement correctly
                        self.nextIndex[idx] = max(append_request.prevLogIndex - 1, 0)
                    else:
                        # Todo: All servers: If RPC request or response contains term T> currentTerm,
                        #  set current term = T, convert to follower
                        self.convToFollowerIfHigherTerm(append_entry_response.term, voted_for=-1)
                # Success
                else:
                    self.logger.info(f"[AP_En]: thread_append_entry to <{idx}> success")
                    self.matchIndex[idx] = last_req_log_idx
                    self.logger.debug(f'[KVStore]: matchIndex: <{self.matchIndex}>')
                    n_list = sorted(self.matchIndex)
                    # TODO: write to disk upon majority
                    # if there exists such N that N> commitIndex and majority of matchIndex[i] >= N
                    # and log[N].term ==currentTerm, set commitIndex = N
                    N = n_list[int(len(n_list) / 2)]
                    if N >= 0 and N > self.commitIndex and self.log[N][0] == self.currentTerm:
                        self.commitIndex = N
                        self.logger.info(f"RAFT: Commit index on leader updates to: {N}")
                        disk_write_kth = KThread(target=self.applyToStateMachine, args=(self.lastApplied,))
                        disk_write_kth.start()
        except Exception as e:
            self.logger.error("[Vote]: f() thread_append_entry, most likely name resolution error")
            self.logger.error(e)  # Todo: Name resolution error

    def appendEntries(self, request, context):  # receiving/server side
        # int32 term = 1;
        # int32 leaderID = 2;
        # int32 prevLogIndex = 3;
        # int32 prevLogTerm = 4;
        # repeated LogEntry entries = 5;
        # int32 leaderCommit = 6;
        self.leaderID = request.leaderID
        if random.uniform(0, 1) < self.cmserver.fail_mat[self.leaderID][self.id]:
            self.logger.warning(f'[ABORTED]: append entries from server <{self.leaderID}> '
                                f'to <{self.id}>, because of ChaosMonkey')
        else:
            # Todo: if election timeout elapse without receiving AppendEntries RPC from current leader or granting vote
            #  to candidate: convert to candidate
            self.lastUpdate = time.time()
            success = False
            try:
                # Todo: If candidates receive AppendEntries RPC from a leader, convert to follower
                #  mcip: request term should be useless coz of last log term??????
                if self.role == KVServer.candidate:
                    self.save(current_term=max(self.lastLogTerm, request.term), voted_for=-1)
                    self.role = KVServer.follower
                    with self.candidateCond:
                        self.candidateCond.notify_all()
                else:
                    # Todo: All servers: If RPC request or response contains term T> currentTerm,
                    #  set current term = T, convert to follower
                    self.convToFollowerIfHigherTerm(request.term, voted_for=-1)

                tmp_entries = []
                for row in request.entries:
                    r = [row.term, row.key, row.val]
                    tmp_entries.append(r)
                    # self.logger.info(f'row: <{r}>')
                # reply false if term < currentTerm,
                # or log doesn't log doesn't contain an entry at prevLogIndex whose term matches prevLogTerm
                # Todo: if it doesn't match the term, it will decrement and resend, thus following will remove entries
                if request.term < self.currentTerm or request.prevLogIndex > len(self.log) \
                        or (request.prevLogIndex < len(self.log) and
                            self.log[request.prevLogIndex][0] != request.prevLogTerm):

                    self.logger.warning(f'[AP_En]: received on <{self.id}>, will return false to <{self.leaderID}>')
                    self.logger.warning(f'[AP_En]: <{request.term < self.currentTerm}>, '
                                        f'<{request.prevLogIndex > len(self.log)}>, '
                                        f'<{(request.prevLogIndex < len(self.log) and self.log[request.prevLogIndex][0] != request.prevLogTerm)}>')
                    self.logger.info(f'Parameters for false: req term: <{request.term}>, cur term: '
                                     f'<{self.currentTerm}>, req prevLogIdx: <{request.prevLogIndex}>, '
                                     f'length of server log <{len(self.log)}>')
                    if request.prevLogIndex < len(self.log):
                        self.logger.info(f'term of log on prev log index: <{self.log[request.prevLogIndex][0]}>, '
                                         f'request prev log term: <{request.prevLogTerm}>')
                        #     existing entry conflicts with a new one, same idx different terms,
                        #     delete the existing entry and all that follow it
                        # self.logger.info(f'RAFT: checking conflicting entries')
                        itr = 0
                        for a, b in zip(tmp_entries, self.log[request.prevLogIndex:]):
                            if a != b:
                                self.logger.warning(f'[Log]: Found conflict at index: '
                                                    f'<{request.prevLogIndex + itr}>')
                                self.logModify(request.prevLogIndex + itr, LogMod.DELETION)
                            itr += 1
                else:
                    self.save(current_term=max(self.currentTerm, request.term), voted_for=-1)
                    # self.logger.info("RAFT: AppendEntries should succeed unless there is conflict entries")
                    success = True
                    #     existing entry conflicts with a new one, same idx different terms,
                    #     delete the existing entry and all that follow it
                    # self.logger.info(f'RAFT: checking conflicting entries')
                    itr = 0
                    if len(self.log) > 0:
                        for a, b in zip(tmp_entries, self.log[request.prevLogIndex:]):
                            if a != b:
                                self.logger.warning(f'[Log]: Found conflict at index: '
                                                    f'<{request.prevLogIndex + itr}>')
                                self.logModify(request.prevLogIndex + itr, LogMod.DELETION)
                            itr += 1
                    # Heartbeat
                    if len(tmp_entries) == 0:
                        self.logger.info("[Log]: received a heartbeat")
                    # Normal append entries
                    else:
                        self.logger.info(f"[Log]: append entries, leader commit <{request.leaderCommit}>")
                        # Append any new entries not already in the log
                        to_append_length = request.prevLogIndex + len(tmp_entries) - len(self.log)
                        # self.logger.debug(f'RAFT: length of log to append: <{to_append_length}>')
                        if to_append_length > 0:
                            self.logModify(tmp_entries[-to_append_length:], LogMod.ADDITION)
                        # If leaderCommit > commitIndex, set commitIndex = min(leaderCommit, index of last new entry)
                        # print("Received log from appendEntries is: ", tmp_entries)
                        # self.logger.debug(f'RAFT: Checking if we need to write to disk: <{request.leaderCommit}>,'
                        #                   f'<{self.commitIndex}>, <{self.lastLogIndex}>')
                        if request.leaderCommit > self.lastApplied:
                            self.logger.info(f"[Log]: apply to state machine, leader commit <{request.leaderCommit}> "
                                             f"last applied <{self.lastApplied}>")
                            self.commitIndex = min(request.leaderCommit, self.lastLogIndex)
                            app_state_mach_kth = KThread(target=self.applyToStateMachine, args=(self.lastApplied,))
                            app_state_mach_kth.start()
                    # int32 term = 1;
                    # bool success = 2;
                self.lastUpdate = time.time()
                return kvstore_pb2.AppendResponse(term=self.currentTerm, success=success)
            except Exception as e:
                self.logger.error("RAFT[Vote]: f(): appendEntries:")
                self.logger.error(e)

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
        if self.id == self.leaderID:
            self.matchIndex[self.id] = self.lastLogIndex
            # Wait until last committed entry is from leader's term, notify all upon leader's log change
            with self.lastCommittedTermCond:
                self.lastCommittedTermCond.notify_all()
        if self.lastLogTerm > self.currentTerm:
            self.save(current_term=self.lastLogTerm, voted_for=self.votedFor)
        self.logger.info(f'[Log]: Log updated on disk of server <{self.id}> ,'
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
        # Apply command in log order, notify all upon completion
        with self.appliedStateMachCond:
            self.appliedStateMachCond.notify_all()
        self.logger.info(f'[StateMach]: Last applied index: <{self.lastApplied}>, '
                          f'state machine updated to: <{self.stateMachine}>')

    # def readWithKey(self, key):
    #     n = len(self.log)
    #     for i in range(n - 1, -1, -1):
    #         if self.log[i][1] == key: return self.log[i][2]
    #     return ""

    def run(self):
        # Create a thread to run as follower
        leader_state = KThread(target=self.leader, args=())
        leader_state.start()
        candidate_state = KThread(target=self.candidate, args=())
        candidate_state.start()
        follower_state = KThread(target=self.follower, args=())
        follower_state.start()

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
        try:
            # string key = 1;
            # Reply NOT_LEADER if not leader, providing hint when available
            if self.role != KVServer.leader:
                # string value = 1;
                # ClientRPCStatus status = 2;
                # int32 leaderHint = 3;
                self.logger.info(f'[KVStore]: Get redirect to leader <{self.leaderID}>')
                return kvstore_pb2.GetResponse(value="", status=kvstore_pb2.NOT_LEADER, leaderHint=self.leaderID)
            try:
                # Wait until last committed entry is from leader's term
                with self.lastCommittedTermCond:
                    self.lastCommittedTermCond.wait_for(lambda: self.log[self.commitIndex][0] == self.currentTerm)
                    # Save commitIndex as local variable readIndex
                    read_index = self.commitIndex
                # Todo: Is this done?
                # Send new round of heartbeats, and wait for reply from majority of servers
                with self.appendEntriesCond:
                    self.appendEntriesCond.notify_all()
                # Wait for state machine to advance at least the readIndex log entry
                with self.appliedStateMachCond:
                    self.appliedStateMachCond.wait_for(lambda: self.lastApplied >= read_index)
                # Process query
                # Reply OK with state machine output
                self.logger.info(f'[KVStore]: Get success: <{request.key}, {self.stateMachine[request.key]}>')
                context.set_code(grpc.StatusCode.OK)
                return kvstore_pb2.GetResponse(value=self.stateMachine[request.key], status=kvstore_pb2.OK2CLIENT,
                                               leaderHint=self.id)
            except KeyError:
                self.logger.warning(f'[KVStore]: Get failed, no such key: [{request.key}]')
                context.set_code(grpc.StatusCode.CANCELLED)
                return kvstore_pb2.GetResponse(value="", status=kvstore_pb2.ERROR2CLIENT, leaderHint=self.id)
        except Exception as e:
            self.logger.error("RAFT[KVStore]: f(): Get")
            self.logger.error(e)

    def Put(self, request, context):
        try:
            # string key = 1;
            # string value = 2;
            # int32 clientID = 3;
            # int32 sequenceNum = 4;
            # NOT_LEADER = 0;
            # SESSION_EXPIRED = 1;
            # OK2CLIENT = 2;
            # ERROR2CLIENT = 3;
            # if command received from client: append entry to local log, respond after entry applied to state machine
            # Reply NOT_LEADER if not leader, providing hint when available
            if self.role != KVServer.leader:
                return kvstore_pb2.PutResponse(status=kvstore_pb2.NOT_LEADER, response="", leaderHint=self.leaderID)
            # Reply SESSION_EXPIRED if not record of clientID or if the response for client's sequenceNum
            # already discarded
            if request.clientID not in self.registeredClients or \
                    self.clientReqResults[request.clientID][1] > request.sequenceNum:
                return kvstore_pb2.PutResponse(status=kvstore_pb2.SESSION_EXPIRED, response="", leaderHint=self.leaderID)
            # If sequenceNum already processed from client, reply OK with stored response
            if self.clientReqResults[request.clientID][1] == request.sequenceNum:
                return kvstore_pb2.PutResponse(status=kvstore_pb2.OK2CLIENT,
                                               response=self.clientReqResults[request.clientID][0],
                                               leaderHint=self.leaderID)
            # Todo: Following line has correct order?
            # Append command to log, replicate and commit it
            self.logModify([[self.currentTerm, request.key, request.value]], LogMod.ADDITION)
            put_log_ind = self.lastLogIndex
            # wake up threads to append entries
            with self.appendEntriesCond:
                self.appendEntriesCond.notify_all()
            # Apply command in log order
            with self.appliedStateMachCond:
                self.appliedStateMachCond.wait_for(lambda: (self.lastApplied >= put_log_ind),
                                                   timeout=self.requestTimeout)
            # Save state machine output with sequenceNum for client, discard any prior sequenceNum for client
            self.clientReqResults[request.clientID] = [self.stateMachine[request.key], request.sequenceNum]

            # ClientRPCStatus status = 1;
            # string response = 2;
            # int32 leaderHint = 3;
            # Todo: no need for state machine output for put?
            # Reply OK with state machine output
            if self.lastApplied >= put_log_ind:
                self.logger.info(f'[KVStore]: Server put success on leader <{self.id}>')
                context.set_code(grpc.StatusCode.OK)  # Todo: why is this needed?
                return kvstore_pb2.PutResponse(status=kvstore_pb2.OK2CLIENT, response=self.stateMachine[request.key],
                                               leaderHint=self.id)
            else:
                self.logger.warning(f'[KVStore]: Server put error (timeout?) on leader <{self.id}>')
                context.set_code(grpc.StatusCode.CANCELLED)
                return kvstore_pb2.PutResponse(status=kvstore_pb2.ERROR2CLIENT, response="", leaderHint=self.id)
        except Exception as e:
            self.logger.error("RAFT[KVStore]: f(): Put")
            self.logger.error(e)

    def registerClient(self, request, context):
        try:
            # ClientRPCStatus status = 1;
            # int32 clientID = 2;
            # int32 leaderHint = 3;
            # Reply NOT_LEADER if not leader, provide hint when available
            if self.role != KVServer.leader:
                return kvstore_pb2.RegisterResponse(status=kvstore_pb2.NOT_LEADER, clientID=-1, leaderHint=self.leaderID)
            else:
                # Append register command to log, replicate and commit it
                cur_last_log_ind = len(self.log)
                self.logModify([[self.currentTerm, "client-"+str(cur_last_log_ind), str(cur_last_log_ind)]],
                               LogMod.ADDITION)
                # wake up threads to register clients
                with self.appendEntriesCond:
                    self.appendEntriesCond.notify_all()
                    self.registeredClients.append(cur_last_log_ind)  # Todo: faster if we put following 2 here?
                    self.clientReqResults[cur_last_log_ind] = ["", -1]   # init client result dictionary
                # Apply command in log order, allocating session for new client
                with self.appliedStateMachCond:
                    self.logger.info(f'[Client]: Register client: lastApplied, <{self.lastApplied}>, '
                                      f'cur_last_log_ind, <{cur_last_log_ind}>, matchIndex, <{self.matchIndex}>')
                    self.appliedStateMachCond.wait_for(lambda: self.lastApplied >= cur_last_log_ind)
                # Todo: allocating new session?
                # Reply OK with unique client identifier (the log index of the register command could be used)
                return kvstore_pb2.RegisterResponse(status=kvstore_pb2.OK2CLIENT, clientID=cur_last_log_ind,
                                                    leaderHint=self.leaderID)
        except Exception as e:
            self.logger.error("RAFT[Register]: f(): registerClient")
            self.logger.error(e)

    def clientRequest(self, request, context):
        pass

    def clientQuery(self, request, context):
        pass

    def updateConfigs(self, request, context):
        # int32 requestTimeout = 1;
        # int32 maxElectionTimeout = 2;
        # int32 keySizeLimit = 3;
        # int32 valSizeLimit = 4;
        try:
            self.requestTimeout = request.requestTimeout
            self.maxElectionTimeout = request.maxElectionTimeout
            self.keySizeLimit = request.keySizeLimit
            self.valSizeLimit = request.valSizeLimit
            # ReturnCode ret = 1;
            return kvstore_pb2.UpdateConfigsResponse(ret=kvstore_pb2.SUCCESS)
        except Exception as e:
            self.logger.error("RAFT[ConfigChn]: f(): updateConfigs\n"+e)
            return kvstore_pb2.UpdateConfigsResponse(ret=kvstore_pb2.FAILURE)

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


