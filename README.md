# README
## How to run
Run `gen_proto.sh` to generate python files from `*.proto`

1. Local execution
    - Modify `server-list.csv`
    - `python scripts/run_raft_servers.py`
2. Remote setup (for new machine `pip` environment)
    - Modify `remote-server.csv`
    - `python scripts/run_raft_servers.py remote-server.csv --pem_file path/to/pemfile --remote --setup`
3. Remote exeution
    - `python scripts/run_raft_servers.py remote-server.csv --pem_file path/to/pemfile --remote`
    - If you don't need to sync source code, add `--no_sync`, which can speedup the script

## Implementation details
1.  Three threads representing leader/follower/candidate roles, controlled by 
Condition Variables
2.  Leader thread will send append entry request to each other server with individual thread
3.  Applying to the state machine is done asynchronously with an 
additional thread, which notifies threads that 
require state machine update.
4.  The Connectivity Matrix is implemented as ChaosMonkey; uf node j receives a messages from node i, 
the value (i,j) in the matrix represents the probability that node j will drop the message.
5.  After a server grants vote to another server, its election timeout countdown will restart. 
6.  A local variable consisting of currentTerm is created before a candidate request vote, 
or a leader send append entries request; the currentTerm is updated upon receiving the response.
7.  Application of log[] to state machine is done asynchronously since it shouldn't be in critical path
8.  When a candidate receive appendEntries request, it compares the request term with its last log term 
(instead of candidates currentTerm); if request term is equal or higher, it will convert to follower.

## Implementation and evaluation
* Refer to the research paper in the repository