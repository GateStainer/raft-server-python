#!/bin/bash

sudo pkill python3
python3 src/raft.py $1 --id $2 --server_list_file remote-server.csv