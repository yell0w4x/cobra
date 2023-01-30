from googleapiclient.discovery_cache import LOGGER as google_discovery_cache_logger
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google.oauth2.service_account import Credentials
import io

from os import stat
from logging import ERROR

google_discovery_cache_logger.setLevel(level=ERROR)
SCOPES = ['https://www.googleapis.com/auth/drive']

# class GoogleDrive:
#     SCOPES = ['https://www.googleapis.com/auth/drive']

#     def __init__(self, service_account_key_fn, folder_id):
#         pass


def file_size(filename):
    file_stats = stat(filename)
    # print('File Size in Bytes is {}'.format(file_stats.st_size))
    return file_stats.st_size


def _service(service_acc_key_fn):
    credentials = Credentials.from_service_account_file(service_acc_key_fn, scopes=SCOPES)
    return build('drive', 'v3', credentials=credentials)


def upload_file(service_acc_key_fn, filename, mimetype,
                upload_filename, parent_folder_id, resumable=True, chunksize=262144):
    service = _service(service_acc_key_fn)
    media = MediaFileUpload(filename, mimetype=mimetype, resumable=resumable, chunksize=chunksize)
    body = dict(name=upload_filename, parents=[parent_folder_id])
    
    request = service.files().create(body=body, media_body=media).execute()
    if file_size(filename) > chunksize:
        done = None
        while done is None:
            chunk = request.next_chunk()
            if not chunk:
                continue

            status, done = chunk
            if status:
                yield status

    return request


def download_file(service_acc_key_fn, file_id):
    service = _service(service_acc_key_fn)

    # pylint: disable=maybe-no-member
    request = service.files().get_media(fileId=file_id)
    stream = io.BytesIO()
    downloader = MediaIoBaseDownload(stream, request)
    done = None
    while done is None:
        status, done = downloader.next_chunk()
        if done is None:
            continue

        yield status

    return stream.getvalue()


def folder_list(service_acc_key_fn, folder_id):
    service = _service(service_acc_key_fn)
    results = service.files().list(q=f"'{folder_id}' in parents",
                                   fields='files(id,name,createdTime,modifiedTime,size,md5Checksum)',
                                   corpora='allDrives',
                                   supportsAllDrives=True, 
                                   includeItemsFromAllDrives=True).execute()

    return results.get('files', [])


if __name__ == '__main__':
    # drive_list('../../.temp/4xybox-service-account-key.json')
    # drives_create('../../.temp/4xybox-service-account-key.json')
    # drive_info('../../.temp/4xybox-service-account-key.json')
    upload_file('../../.temp/4xybox-service-account-key.json', 
                './__init__.py', 'application/json', 
                '__init__.py', '100d96r89SxvJvm7ZUqFCOztaiZv6sBIA')
