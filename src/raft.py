from kvstore import KVServer
from chaosmonkey import CMServer
from concurrent import futures
import time
import click
import grpc
import kvstore_pb2_grpc
import chaosmonkey_pb2_grpc
import csv
import logging
import logging.handlers
import sys
import os


@click.command()
@click.argument('address', default='localhost:7000')
@click.argument('id', type=int, default=0)
@click.argument('server_list_file', default='server-list.csv')
def start_server(address, id, server_list_file):
    server_name = f'{id}-{address.replace(":", "-")}'
    logger = logging.getLogger('raft')
    logger.setLevel(logging.INFO)

    # Terminal log output
    term_handler = logging.StreamHandler(sys.stdout)
    term_handler.setLevel(logging.INFO)
    term_handler.setFormatter(logging.Formatter("[%(asctime)s - %(levelname)s]: %(message)s"))
    logger.addHandler(term_handler)
    # Record write-ahead log (wal) once get rpc 'appendEntries'
    os.makedirs('log', exist_ok=True)
    wal_handler = logging.FileHandler(f'log/{server_name}-wal.log')
    wal_handler.setLevel(logging.CRITICAL)
    wal_handler.setFormatter(logging.Formatter("[%(asctime)s - %(levelname)s]: %(message)s"))
    # WARN: this will overwrite the log
    logger.addHandler(wal_handler)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    addr_list = []
    with open(server_list_file, 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            addr_list.append(row['address'])
    kvserver = KVServer(addr_list, id)
    kvstore_pb2_grpc.add_KeyValueStoreServicer_to_server(
        kvserver, server
    )
    chaosmonkey_pb2_grpc.add_ChaosMonkeyServicer_to_server(
        kvserver.cmserver, server
    )
    server.add_insecure_port(address)
    server.start()
    logger.info(f'Server [{server_name}] listening {address}')
    try:
        while True:
            time.sleep(24*60*60)
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == "__main__":
    start_server()
