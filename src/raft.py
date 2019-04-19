from kvstore import KVServer
from chaosmonkey import CMServer
from concurrent import futures
import time
import click
import grpc
import kvstore_pb2_grpc
import chaosmonkey_pb2_grpc
import csv

@click.command()
@click.argument('address', default='localhost:7000')
@click.argument('id', type=int, default=0)
@click.argument('server_list_file', default='server-list.csv')
def start_server(address, id, server_list_file):
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
    print(f'Server [{id}] listening {address}')
    try:
        while True:
            time.sleep(24*60*60)
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == "__main__":
    start_server()