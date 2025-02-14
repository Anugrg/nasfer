
import os
import shutil
import asyncio
import uuid

import json
import fnmatch
from smb.SMBConnection import SMBConnection


# There will be some mechanism to capture userID, password, client_machine_name, server_name and server_ip
# client_machine_name can be an arbitary ASCII string
# server_name should match the remote machine name, or else the connection will be rejected


class ConfigComp:
    def __init__(self, json_data: json):
        self.config = json_data
    
    def get(self, param):
        return self.config.get(param)


def transfer_file_samba_style(target, client_machine_name, file):
    userID = target['USER_ID']
    password = target['PASSWORD']

    server_name = target['SERVER_NAME']
    service_name = target['SERVICE_NAME']
    nas_ip = target['NAS_IP']
    nas_port = target['NAS_PORT']
    src_folder = target['SRC_FOLDER']
    try:
        conn = SMBConnection(userID, password, client_machine_name, server_name, use_ntlm_v2=True)
        assert conn.connect(nas_ip, nas_port)
        with open(f'{src_folder}/{file}', 'rb') as f:
            conn.storeFile(service_name, f'/{file}', f, show_progress=True)

    except Exception as e:
        print(e)
        return False
    
    is_renamed = rename_file(src_folder, file)
    if not is_renamed:
        print('Rename failed!')

    return True


def transfer_to_network_drive(target, file):
    src_folder = target['SRC_FOLDER']
    shutil.copy2(f'{src_folder}/{file}', target['NAS_DRIVE'])
    is_renamed = rename_file(src_folder, file)
    if not is_renamed:
        print('Rename failed...')

    return True


def rename_file(src, file):
    print(f'Renaming {file} ...')
    new_name = uuid.uuid4()
    print(f'{str(new_name)}')
    try:
        shutil.move(f'{src}\{file}', f'{src}\{str(new_name)}.png')
    except Exception as e:
        print(e)
        return False
    return True


def check_latest_file(conf):
    print('Checking for new files')
    status = False
    targets = conf.get("NAS_SERVERS")
    for target in targets:
        src = target['SRC_FOLDER']
        print(f'Searching in {src}')
        for file in os.listdir(target['SRC_FOLDER']):
            if fnmatch.fnmatch(file, 'NEW*.png'):
                print(f'New file discovered in {src} ... Transferring to NAS')
                if conf.get('USE_SAMBA'):
                    print('Using SAMBA protocol')
                    status = transfer_file_samba_style(target, conf.get('CLIENT_MACHINE_NAME'), file)
                else:
                    print('Using mounted network drive')
                    status = transfer_to_network_drive(target, file)

                if not status:
                    print('Transfer failed')
                else:
                    print('Transfer success')



async def run(settings : json):
    print('Starting process')
    conf = ConfigComp(settings)
    interval = conf.get('INTERVAL')
    while True:
        try:
            check_latest_file(conf)
            print(f'Sleeping for {interval} secs')
            await asyncio.sleep(interval)
        except KeyboardInterrupt:
            print('Stopped by user')
            break


if __name__=='__main__':
    with open('app.json', 'r') as f:
        _settings = json.load(f)

    asyncio.run(run(_settings))

