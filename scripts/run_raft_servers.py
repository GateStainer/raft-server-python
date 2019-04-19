import click
import csv
from math import ceil, floor, sqrt
import os


@click.command()
@click.argument('server_list_file', default='server-list.csv')
@click.argument('template_file', default='scripts/tmux_template.yaml')
@click.option('--remote', is_flag=True)
def gen_run_script(server_list_file, template_file, remote):
    servers = []
    with open(server_list_file, 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            servers.append(dict(row))
    script = ''
    with open(template_file, 'r') as file:
        script += file.read()
    for s in servers:
        script += f'    - reset && python src/raft.py {s["address"]} {s["id"]} server-list.csv\n'
    with open('launch_raft.yaml', 'w') as file:
        file.write(script)
    os.system('tmuxp load launch_raft.yaml')


if __name__ == "__main__":
    gen_run_script()
