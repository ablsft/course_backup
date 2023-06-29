import requests
import os.path
import logging
import json
from datetime import datetime
from io import BytesIO

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload

class VKPhotoDownloader:
    def __init__(self, token_vk: str):
        self.token_vk = token_vk

    def get_albums_list(self, owner_id='1'):
        url = 'https://api.vk.com/method/photos.getAlbums'

        params = {
            'owner_id': owner_id,
            'access_token': self.token_vk,
            'v': '5.131'
        }

        res = requests.get(url, params=params)
        print()

        if res.status_code == 200 and 'response' in res.json():
            print(f"\nUser with id '{owner_id}' has the following albums (id, 'title'):\n")

            for item in res.json()['response']['items']:
                print(f"{item['id']}, '{item['title']}'")
        
            print("wall, 'фотографии со стены'")
            print("profile, 'фотографии профиля'")
            print("saved, 'сохраненные фотографии'")
        
        else:
            logging.error(f'Error while getting albums list. Please check vk token')

    def get_links(self, owner_id='1', album_id='profile', count=5):
        url = 'https://api.vk.com/method/photos.get'

        params = {
            'owner_id': owner_id,
            'album_id': album_id,
            'count': str(count),
            'extended': '1',
            'access_token': self.token_vk,
            'v': '5.131'
        }

        res = requests.get(url, params=params)

        if res.status_code == 200 and 'response' in res.json():
            photos = []
            sizes_ascending = {'s': 1, 'm': 2, 'o': 3, 'p': 4, 'q': 5,
                               'r': 6, 'x': 7, 'y': 8, 'z': 9, 'w': 10} 

            for item in res.json()['response']['items']:
                sizes = item['sizes']
                sizes.sort(key=lambda x: sizes_ascending[x['type']])
                photos.append({'file_name': item['likes']['count'],
                            'url': sizes[-1]['url'],
                            'type': sizes[-1]['type'],
                            'date': item['date']})
            
            print()
            logging.info(f"All links for {count} photos from album '{album_id}' obtained successfully")
            
            photos.sort(key=lambda d: d['file_name'])
            photos = self.edit_filename(photos) + [owner_id, album_id]

            return photos

        else:
            print()
            logging.error(f'Error while obtaining links for photos')
    
    def edit_filename(self, photos):
        for i in range(len(photos)-1):
            if photos[i]['file_name'] == photos[i+1]['file_name']:
                date_1 = datetime.fromtimestamp(photos[i]['date']).strftime('%d-%m-%y')
                date_2 = datetime.fromtimestamp(photos[i+1]['date']).strftime('%d-%m-%y')

                photos[i]['file_name'] = f"{photos[i]['file_name']}({date_1})"
                photos[i+1]['file_name'] = f"{photos[i+1]['file_name']}({date_2})"

        return photos
    

class YaUploader:
    def __init__(self, token_yandex: str):
        self.token_yandex = token_yandex

    def make_folder(self, folder_path: str):
        url = 'https://cloud-api.yandex.net/v1/disk/resources'
            
        params = {
            'path': folder_path 
        }
        headers = {
            'Authorization': self.token_yandex
        }

        res = requests.put(url, headers=headers, params=params)

        if res.status_code == 201:
            print()
            logging.info(f'Folder "{folder_path}" created successfully (Yandex Disk)')
        elif res.status_code == 409:
            print()
            logging.warning(f'Error while creating folder "{folder_path}": already exists (Yandex Disk)')
        else:
            print()
            logging.error(f'Error while creating folder "{folder_path}". Please check if yandex token is correct (Yandex Disk)')

        return folder_path

    def upload(self, data):
        folder = self.make_folder(f'id{data[-2]}_{data[-1]}')

        url = 'https://cloud-api.yandex.net/v1/disk/resources/upload'

        for photo in data[:-2]:
            params = {
                'path': f"{folder}/{photo['file_name']}.jpg",
                'url': photo['url']
            }
            headers = {
                'Authorization': self.token_yandex
            }

            res = requests.post(url, headers=headers, params=params)

            if res.status_code == 202:
                logging.info(f'File "{photo["file_name"]}.jpg" successfully uploaded to folder "{folder}" (Yandex Disk)')

            else:
                logging.error(f'Error while uploading file "{photo["file_name"]}.jpg" to folder "{folder}" (Yandex Disk)')


class GoogleUploader:
    def __init__(self, secrets_filename):
        SCOPES = ['https://www.googleapis.com/auth/drive']
        self.creds = None

        if os.path.exists('token.json'):
            self.creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            
        try:
            if not self.creds or not self.creds.valid:
                if self.creds and self.creds.expired and self.creds.refresh_token:
                    self.creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        secrets_filename, SCOPES)
                    self.creds = flow.run_local_server(port=0)

                with open('token.json', 'w') as token:
                    token.write(self.creds.to_json())

        except FileNotFoundError:
            print()
            logging.error(f'File "{secrets_filename}" not found. Unable to authorize to Google Drive')
        
    def make_folder(self, folder_path: str):
        try:
            service = build('drive', 'v3', credentials=self.creds)
            folder_metadata = {
                'name': folder_path,
                'mimeType': 'application/vnd.google-apps.folder'
            }

            folder = service.files().create(body=folder_metadata, 
                                            fields='id').execute()
            
            print()
            logging.info(f'Folder "{folder_path}" created successfully (Google Drive)')

            return folder.get('id')
        
        except HttpError:
            print()
            logging.error(f'Error while creating folder "{folder_path}". (Google Drive)')

    def upload(self, data):
        folder = self.make_folder(f'id{data[-2]}_{data[-1]}')
        service = build('drive', 'v3', credentials=self.creds)
        
        for photo in data[:-2]:
            try:
                file_metadata = {
                    'name': f"{photo['file_name']}.jpg",
                    'parents': [folder]
                }

                temp_image = requests.get(photo['url'])
                media = MediaIoBaseUpload(BytesIO(temp_image.content), 
                                          mimetype='image/jpeg')
                file = service.files().create(body=file_metadata, 
                                              media_body=media, 
                                              fields='id').execute()
            
                logging.info(f'File "{photo["file_name"]}.jpg" successfully uploaded to folder "id{data[-2]}_{data[-1]}" (Google Drive)')

            except HttpError:
                logging.error(f'Error while uploading file "{photo["file_name"]}.jpg" to folder "id{data[-2]}_{data[-1]}" (Google Drive)')


def make_json(data, filename):
    photos_info = []
    for photo in data[:-2]:
        photos_info.append({'file_name': f"{photo['file_name']}.jpg",
                            'size': photo['type']})
    
    with open(filename, 'w') as write_file:
        json.dump(photos_info, write_file)

    print()
    logging.info(f"File {filename} created successfully")
        

file_log = logging.FileHandler('backup_log.log')
console_out = logging.StreamHandler()
logging.basicConfig(handlers=(file_log, console_out), level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')

logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)


token_vk = ''
downloader = VKPhotoDownloader(token_vk)

print("Enter vk user id: ")
vk_id = input()
albums_list = downloader.get_albums_list(vk_id)

print("\nEnter the id of album to download: ")
album_name = input()
photo_links = downloader.get_links(vk_id, album_name)

print("\nEnter yandex token: ")
token_yandex = input()
ya_uploader = YaUploader(token_yandex)
upload_res_ya = ya_uploader.upload(photo_links)

make_json(photo_links, 'files_info.json')

g_uploader = GoogleUploader('credentials.json')
upload_res_g = g_uploader.upload(photo_links)
