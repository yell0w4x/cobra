from cobra.aux_stuff import rand_str

from googleapiclient.discovery_cache import LOGGER as google_discovery_cache_logger
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google.oauth2.service_account import Credentials
import io
import os
import shutil
from os import stat
from os.path import join, abspath, realpath, exists
from logging import ERROR

google_discovery_cache_logger.setLevel(level=ERROR)
SCOPES = ['https://www.googleapis.com/auth/drive']


def file_size(filename):
    file_stats = stat(filename)
    return file_stats.st_size


def _service(service_acc_key_fn):
    credentials = Credentials.from_service_account_file(service_acc_key_fn, scopes=SCOPES)
    return build('drive', 'v3', credentials=credentials)


def upload_file(service_acc_key_fn, filename, mimetype,
                upload_filename, parent_folder_id, resumable=True, chunksize=262144):
    service = _service(service_acc_key_fn)
    media = MediaFileUpload(filename, mimetype=mimetype, resumable=resumable, chunksize=chunksize)
    body = dict(name=upload_filename, parents=[parent_folder_id])
    
    request = service.files().create(body=body, media_body=media)
    done = None
    while done is None:
        chunk = request.next_chunk()
        if not chunk:
            continue

        status, done = chunk
        if status:
            yield status

    return request


DOWNLOAD_CHUNK_SIZE = 20*1024*1024

def download_file(service_acc_key_fn, file_id, local_dir=None, use_cache=True, chunksize=DOWNLOAD_CHUNK_SIZE):
    service = _service(service_acc_key_fn)

    # pylint: disable=maybe-no-member
    metadata = service.files().get(fileId=file_id).execute()
    fn = metadata['name']
    yield fn
    if local_dir:
        local_dir = realpath(abspath(local_dir))
        if not os.access(local_dir, os.W_OK):
            raise FileNotFoundError(f'Target directory is not found or not accessible [{local_dir}]')

        temp_fn = join(local_dir, rand_str(16))
        full_fn = join(local_dir, fn)
        if use_cache and exists(full_fn):
            return full_fn

    request = service.files().get_media(fileId=file_id)
    with io.FileIO(temp_fn, 'wb') if local_dir else io.BytesIO() as stream:
        downloader = MediaIoBaseDownload(stream, request, chunksize=chunksize)
        while True:
            status, done = downloader.next_chunk()
            yield status
            if done:
                break

        if local_dir:
            shutil.move(temp_fn, full_fn)
            return full_fn

        return stream.getvalue(), fn


def folder_list(service_acc_key_fn, folder_id):
    service = _service(service_acc_key_fn)
    results = service.files().list(q=f"'{folder_id}' in parents",
                                   fields='files(id,name,createdTime,modifiedTime,size,md5Checksum)',
                                   corpora='allDrives',
                                   supportsAllDrives=True, 
                                   includeItemsFromAllDrives=True,
                                   orderBy='createdTime').execute()

    return results.get('files', [])
