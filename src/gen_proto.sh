#! /bin/bash
python -m grpc_tools.protoc -I. --python_out=./src/ --grpc_python_out=./src/ ./src/kvstore.proto
python -m grpc_tools.protoc -I. --python_out=./src/ --grpc_python_out=./src/ ./src/chaosmonkey.proto
