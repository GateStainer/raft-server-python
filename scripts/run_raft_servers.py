import click
import csv
from math import ceil, floor, sqrt
import os


@click.command()
@click.argument('server_list_file', default='server-list.csv')
@click.argument('template_file', default='scripts/tmux_template.yaml')
@click.option('--remote', is_flag=True)
@click.option('--pem_file', type=str)
@click.option('--no_exec', is_flag=True)
@click.option('--setup', is_flag=True)
def gen_run_script(server_list_file, template_file, remote, no_exec, pem_file, setup):
    servers = []
    with open(server_list_file, 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            servers.append(dict(row))
    script = ''
    with open(template_file, 'r') as file:
        script += file.read()
    for s in servers:
        if remote is True:
            remote_exec = f'ssh -i {pem_file} ubuntu@{s["address"]}'
            if setup is True:
                script += f'    - shell_command:\n'
                # script += f'      - {remote_exec} sudo apt install python3-pip -y\n'
                # script += f'      - {remote_exec} sudo pip3 install grpcio\n'
                script += f'      - {remote_exec} sudo pip3 install grpcio-tools\n'
            else:
                script += f'    - shell_command:\n'
                script += f'      - rsync -r -v -a --delete -P -e "ssh -i {pem_file}" *.csv ubuntu@{s["address"]}:/home/ubuntu/raft/\n'
                script += f'      - rsync -r -v -a --delete -P -e "ssh -i {pem_file}" ./src/  ubuntu@{s["address"]}:/home/ubuntu/raft/src\n'
                script += f'      - {remote_exec} cd /home/ubuntu/raft && python3 src/raft.py 0.0.0.0:{s["port"]} --id {s["id"]} --server_list_file remote-server.csv\n'
        else:
            script += f'    - reset && python src/raft.py {s["address"]}:{s["port"]} --id {s["id"]} server-list.csv\n'
    with open('launch_raft.yaml', 'w') as file:
        file.write(script)
    if not no_exec:
        os.system('tmuxp load launch_raft.yaml')


if __name__ == "__main__":
    gen_run_script()
