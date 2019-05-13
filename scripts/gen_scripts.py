import csv
import os
import click

@click.command()
@click.argument('server_list_file', default='remote-server.csv')
@click.option('--pem_file', default='xipu.pem')
def gen_fetchLog_script(server_list_file, pem_file):
	servers = []
	with open(server_list_file, 'r') as file:
		reader = csv.DictReader(file)
		for row in reader:
			servers.append(dict(row))
	script = ''
	script += 'rm log/*\n'
	for s in servers:
		script += f'scp -i {pem_file} ec2-user@{s["address"]}:/home/ec2-user/raft/log/*.txt  log/\n'
	with open('fetchLog.sh', 'w') as file:
		file.write(script)
	os.system('bash fetchLog.sh')

if __name__ == "__main__":
	gen_fetchLog_script()
            
