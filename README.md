# README

1. Local execution
    - Modify `server-list.csv`
    - `python scripts/run_raft_servers.py`
2. Remote setup (for new machine `pip` environment)
    - Modify `remote-server.csv`
    - `python scripts/run_raft_servers.py remote-server.csv --pem_file path/to/pemfile --remote --setup`
3. Remote exeution
    - `python scripts/run_raft_servers.py remote-server.csv --pem_file path/to/pemfile --remote`
    - If you don't need to sync source code, add `--no_sync`, which can speedup the script