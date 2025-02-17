
import os
import shutil
import asyncio
import uuid
from threading import Thread
from datetime import datetime as dt
from queue import Queue
from pathlib import Path

import json
import fnmatch
from watchfiles import awatch
from smb.SMBConnection import SMBConnection
  

# There will be some mechanism to capture userID, password, client_machine_name, server_name and server_ip
# client_machine_name can be an arbitary ASCII string
# server_name should match the remote machine name, or else the connection will be rejected


class CopyThread(Thread):

    def __init__(self, queue, _func):
        Thread.__init__(self)
        print('init thread')
        self.queue = queue
        self._func = _func

    def run(self):
        while True:
            data = self.queue.get()
            print(f'Moving file {data[0]} --- {dt.now()}')
            self._func(*data)
            print(f'Completed --- {dt.now()}')
            self.queue.task_done()


class ConfigComp:
    def __init__(self, json_data: json):
        self.config = json_data

    def get(self, param):
        return self.config.get(param)


def transfer_file_samba_style(*args):
    file = args[0]
    target = args[1]
    client_machine_name = args[2]

    userID = target['USER_ID']
    password = target['PASSWORD']
    server_name = target['SERVER_NAME']
    service_name = target['SERVICE_NAME']
    nas_ip = target['NAS_IP']
    nas_port = target['NAS_PORT']

    new_name = uuid.uuid4()
    try:
        conn = SMBConnection(userID, password, client_machine_name, server_name, use_ntlm_v2=True)
        assert conn.connect(nas_ip, nas_port)
        with open(f'{file}', 'rb') as f:
            conn.storeFile(service_name, f'/{str(new_name)}.png', f, show_progress=True)

    except Exception as e:
        print(e)
        return False

    # is_renamed = rename_file(file)
    # if not is_renamed:
    #     print('Rename failed!')

    return True


def transfer_to_network_drive(*args):
    file = args[0]
    target = args[1]
    
    src_folder = target['SRC_FOLDER']
    #shutil.copy2(f'{src_folder}/{file}', target['NAS_DRIVE'])
    shutil.copy2(file, target['NAS_DRIVE'])
    # is_renamed = rename_file(file)
    # if not is_renamed:
    #     print('Rename failed...')

    return True


def rename_file(file):
    print(f'Renaming {file} ...')
    new_name = uuid.uuid4()
    print(f'{str(new_name)}')
    try:
        #shutil.move(f'{src}\{file}', f'{src}\{str(new_name)}.png')
        shutil.move(file, f'{Path(file).parent}\\{str(new_name)}.png')
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


async def run2(settings):
    print('Starting process')
    conf = ConfigComp(settings)
    queue = Queue()

    for _ in range(2):
        if conf.get('USE_SAMBA'):
            t = CopyThread(queue, transfer_file_samba_style)
        else:
            t = CopyThread(queue, transfer_to_network_drive)

        t.daemon = True
        t.start()

    files = [nas_info['SRC_FOLDER'] for nas_info in conf.get('NAS_SERVERS')]
    while True:
        async for changes in awatch(*files):
            for change in changes:
                if change[0] == 1:
                    print('Queueing task...')
                    for target in conf.get('NAS_SERVERS'):
                        print(target)
                        print(str(Path(change[1])))
                        if target['SRC_FOLDER'] == str(Path(change[1]).parent):
                            if conf.get('USE_SAMBA'):
                                print('using samba')
                                queue.put((change[1], target, conf.get('CLIENT_MACHINE_NAME')))
                            else:
                                print('normal copy')
                                queue.put((change[1], target))

        queue.join()


if __name__=='__main__':
    with open('app.json', 'r') as f:
        _settings = json.load(f)

    asyncio.run(run2(_settings))

