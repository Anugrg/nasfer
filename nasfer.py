
import os
import shutil
import asyncio
import uuid
from threading import Thread
from datetime import datetime as dt
from queue import Queue
from pathlib import Path
import logging


import json
import fnmatch
from watchfiles import awatch, Change
from smb.SMBConnection import SMBConnection
from smb.smb_structs import OperationFailure
  

# There will be some mechanism to capture userID, password, client_machine_name, server_name and server_ip
# client_machine_name can be an arbitary ASCII string
# server_name should match the remote machine name, or else the connection will be rejected


def show_only_info(record):
    return record.levelname == "INFO"


# create logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)


file_handler = logging.FileHandler("app.log", mode="a", encoding="utf-8")

formatter = logging.Formatter(
    "{asctime} - {levelname} - {message}",
    style="{",
    datefmt="%Y-%m-%d %H:%M",
)
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

console_handler.addFilter(show_only_info)

logger.addHandler(console_handler)
logger.addHandler(file_handler)



class CopyThread(Thread):

    def __init__(self, queue, _func):
        Thread.__init__(self)
        logger.debug('Starting thread ok')
        self.queue = queue
        self._func = _func

    def run(self):
        while True:
            data = self.queue.get()

            self._func(*data)
            logger.info(f'Transfer completed --- {dt.now()}')
            self.queue.task_done()


class ConfigComp:
    def __init__(self, json_data: json):
        logger.debug('Reading config file ok')
        self.config = json_data

    def get(self, param):
        return self.config.get(param)


def match_dir_nas(conn, dir_name, service_name):
    exists = False
    print(dir_name)
    for i in conn.listPath(service_name, '/'):

        if i.isDirectory and i.filename == dir_name:
            exists =  True

    return exists


def create_dir_nas(conn, service_name, dir):
    try:
        conn.createDirectory(service_name, f'/{dir}')
    except OperationFailure:
     logger.error('Failed to create directory', exc_info=True)


def get_full_paths(directory_dict):
    full_paths = {}
    for parent, child in directory_dict.items():
        if parent in full_paths:
            full_paths[child] = os.path.join(full_paths[parent], child).replace('\\', '/')
        else:
            full_paths[child] = os.path.join('/', parent, child).replace('\\', '/')
    return full_paths


def transfer_file_samba_style(*args):
    print('transferring')
    file = args[0]
    target = args[1]
    client_machine_name = args[2]
    file_paths = file.split('\\')
    file_paths.pop(0)
    file_paths.pop(0)
    
    userID = target['USER_ID']
    password = target['PASSWORD']
    server_name = target['SERVER_NAME']
    service_name = target['SERVICE_NAME']
    nas_ip = target['NAS_IP']
    nas_port = target['NAS_PORT']
    new_name = uuid.uuid4()
    dests = target['DEST_FOLDER'].split('/')
    print(dests)
    directory_dict = {}
    for i in range(len(dests) - 1):
        directory_dict[dests[i]] = dests[i + 1]

    name =  os.path.basename(file)
    print(name)
    full_paths = get_full_paths(directory_dict)
    full_paths[dests[0]] = f'/{dests[0]}'
    final_path = full_paths[dests[-1]] 
    print(final_path)
    print(full_paths)
    
    conn = SMBConnection(userID, password, client_machine_name, server_name, use_ntlm_v2=True)
    assert conn.connect(nas_ip, nas_port)
    for dest in dests:
        if not match_dir_nas(conn, full_paths[dest], service_name):
            create_dir_nas(conn, service_name, full_paths[dest])


    # _date = dt.today()
    # dir_name = _date.strftime('%Y_%m_%d')
    # hr_dir = _date.strftime('%H')


    # exists = match_dir_nas(conn, dir_name, service_name)

    # # check if date directory exists
    # if not exists:
    #     create_dir_nas(conn, service_name, dir_name)
    
    # # check if hr directory exists
    # exists = match_dir_nas(conn, f'/{dir_name}/{hr_dir}', service_name)

    # if not exists:
    #     create_dir_nas(conn, service_name, f'{dir_name}/{hr_dir}')
    name =  os.path.basename(file)
    print(name) 
    try:
        with open(f'{file}', 'rb') as f:
            #conn.storeFile(service_name, f'/{dir_name}/{hr_dir}/{new_name}.png', f, show_progress=True)
            conn.storeFile(service_name, f'/{final_path}/{name}', f, show_progress=True)

    except Exception as e:
        logger.error('Failed to transfer', exc_info=True)
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
    try:
        shutil.copy2(file, target['NAS_DRIVE'])
    except Exception as e:
        logger.error('Network drive failure', exc_info=True)
    # is_renamed = rename_file(file)
    # if not is_renamed:
    #     print('Rename failed...')

    return True


def rename_file(file):
    logger.info('Renaming file')
    new_name = uuid.uuid4()
    logger.info("New name: %s", new_name)
    try:
        shutil.move(file, f'{Path(file).parent}\\{str(new_name)}.png')
    except Exception as e:
        logging.error("Error during rename", exc_info=True)
        return False

    return True


def check_latest_file(conf):

    status = False
    targets = conf.get("NAS_SERVERS")
    pattern = conf.get('pattern')
    try:
        for target in targets:
            src = target['SRC_FOLDER']
            print(f'Searching in {src}')
            for file in os.listdir(target['SRC_FOLDER']):
                if fnmatch.fnmatch(file, f'{pattern}.png'):
                    logger.info(f'New file discovered in {src} ... Transferring to NAS')
                    if conf.get('USE_SAMBA'):
                        logger.info('Using SAMBA protocol')
                        status = transfer_file_samba_style(target, conf.get('CLIENT_MACHINE_NAME'), file)
                    else:
                        logger.info('Using mounted network drive')
                        status = transfer_to_network_drive(target, file)

                    if not status:
                        print('Transfer failed')
                    else:
                        print('Transfer success')
    except Exception as e:
        logger.error("Error during checking file", exc_info=True)


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
            logging.error("User pressed key", exc_info=True)
            break


def only_added(change: Change, path: str) -> bool:
    return change == Change.added


async def run2(settings):
    logger.info('Listening for new file event...')
    conf = ConfigComp(settings)
    queue = Queue()
    try:
        for _ in range(2):
            if conf.get('USE_SAMBA'):
                t = CopyThread(queue, transfer_file_samba_style)
            else:
                t = CopyThread(queue, transfer_to_network_drive)

            t.daemon = True
            t.start()
    except Exception as e:
        logger.error("Thread creation failed", exc_info=True)
        

    files = [nas_info['SRC_FOLDER'] for nas_info in conf.get('NAS_SERVERS')]    

    try:
        while True:
            async for changes in awatch(*files, watch_filter=only_added):
                for change in changes:
  
                    for target in conf.get('NAS_SERVERS'):

                        if target.get('CAM') in str(Path(change[1]).parent):
                            
                            if conf.get('USE_SAMBA'):

                                queue.put((change[1], target, conf.get('CLIENT_MACHINE_NAME')))
                            else:

                                queue.put((change[1], target))


            queue.join()

    except Exception as e:
        logger.error("Error with file transfer", exc_info=True)


if __name__=='__main__':
    logger.info('Starting program')
    try:
        with open('app.json', 'r') as f:
            _settings = json.load(f)
    except Exception as e:
        logger.error("Can't open config json file", exc_info=True)
    if _settings.get('mode'):
        asyncio.run(run2(_settings))
    else:
        asyncio.run(run(_settings))

