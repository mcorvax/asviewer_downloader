#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import mimetypes
import os
import random
import re
import requests
import sys
import time
import yaml

from datetime import datetime

configFile = 'configuration.yaml'
headersFile = 'headers.yaml'

class State:
    def __init__(self):
        self.headers = {}
        self.proxies = {}
        self.remoteHost = 'https://gato.tularegion.ru'
        self.viewerPath = '/srv/imageViewer/image?url='
        self.baseURL = self.remoteHost + self.viewerPath
        self.authURL = self.remoteHost + '/auth'
        self.loginURL = self.remoteHost + '/login'
        self.apiURL = 'https://gato.tularegion.ru/private_api'
        self.remotePath = ''
        self.start = 1
        self.end = None 
        self.token = None
        self.allowedSpendMoney = False
        self.config = {}
        self.config['local'] = {}
        self.config['local']['directory'] = datetime.now().strftime('%Y-%m-%d_%H:%M:%S')
        self.config['local']['destination'] = ''
        self.config['remote'] = {}
        self.config['remote']['username'] = None
        self.config['remote']['password'] = None
        self.session = requests.Session()
 
    def init_proxies(self) -> None:
        for key in self.config['proxy']:
            if self.config['proxy'][key] is not None and self.config['proxy'][key] != '':
                self.proxies[key] = str(self.config['proxy'][key])

    def load_config(self, file_path: str) -> None:
        with open(file_path, 'r') as file:
            self.config = yaml.load(file, Loader=yaml.Loader)
        
        # for key in self.config:
        #     self.config[key] = str(self.config[key])

        if 'remote' in self.config and 'loginUrl' in self.config['remote']:
            self.authURL = self.config['remote']['loginUrl']

    def load_headers(self, file_path: str) -> None:
        with open(file_path, 'r') as file:
            self.headers = yaml.safe_load(file)
        # stringyfing all values in headersData as requests only accepts strings
        
        del self.headers['Cookie']
        for key in self.headers:
            self.headers[key] = str(self.headers[key])
        
        if 'Host' in self.headers:
            self.baseURL = 'https://' + self.headers['Host']
            
            del self.headers['Host']

        if 'GET' in self.headers:
            self.remotePath = str(self.headers['GET']).split(" ")[0]
            del self.headers['GET']
            self.remotePath = self.baseURL + '/' + self.remotePath
            
    def __del__(self):
        self.session.close()
        
    def authenticate(self, loc: str | None) -> bool:
        """Authenticate the user and store the token."""
        if loc and loc.startswith(self.remoteHost+'/private/subscription'):
            return self.activate_subscription()
        
        if loc and not loc.startswith(self.loginURL):
            print(f"Got a new redirect: {loc}. Don't know what to do...") 
            return False
        
        print('Trying authenticate...')
        if not ('remote' in self.config
                and 'username' in self.config['remote'] and self.config['remote']['username'] > ''
                and 'username' in self.config['remote'] and self.config['remote']['username'] >''):
            return False
        headers = self.headers
        headers['Content-Type'] = 'application/json'
        headers['Referer'] = self.config['remote']['loginURL']
        headers['Accept'] = 'application/json, text/plain, */*'
        
        self.session.cookies.set('auth.strategy', 'local')
        self.session.cookies.set('auth._token.local', 'false')
        self.session.cookies.set('auth._token_expiration.local', 'false')
        self.session.cookies.set('auth.redirect', '/private/me')

        payload = {
            'username': self.config['remote']['username'],
            'password': self.config['remote']['password']
        }
        try:
            response = self.session.get(self.authURL, headers=headers, proxies=self.proxies, json=payload)
            if response.status_code != 200:
                print(f"Authentication failed: {response.status_code} - {response.reason}")
                return False
        except requests.RequestException as e:
            print(f"Error during authentication: {e}")
            return False
        
        self.token = response.json()['token']
        self.session.cookies.set("auth._token.local", f"Bearer {self.token}")
        self.headers['Authorization'] = f"Bearer {self.token}"
        print('Authenticated!')
        return True

    def api_request(self, method: str, payload: list | dict | None) -> dict:
        try:
            response = self.session.post(self.apiURL+'/'+method, headers=self.headers, proxies=self.proxies, json=payload)
            if response.status_code not in [200, 202]:
                print(f"API request failed: {response.status_code} - {response.reason}")
                return {}
        except requests.RequestException as e:
            print(f"Error during authentication: {e}")
            return {}
        return response.json()

    def get_subscriptions(self) -> str | None:
        list = self.api_request('get-subscr', {'languageId': 1})
        count = 0
        try:
            count = list['value'][0]['count']
        except:
            print("Can't get a number of subscriptions")
        if count == 0:
            return
        return list['value'][0]['id']

    def activate_subscription(self) -> bool:
        if not self.allowedSpendMoney:
            print('Activation of the purchased subscription is not allowed automatically. Please activate it manually.')
            time.sleep(3)
            return False
        
        subscription_id = self.get_subscriptions()
        if not subscription_id:
            print("Your subscription has expired. To continue, please purchase a new one on the site.")
            return False
        
        #[{"id":3077447665,"count":1}]
        data = [{'id': subscription_id, 'count': 1}]
        result = self.api_request('activate-subscr', data)
        
        #{"value":"success","success":true,"message":null,"e":null}
        if not result['success']:
            print("Subscription activation failed. Please visit the site to check what’s going on.")
            return False
        print("Subscription successfully activated!")
        return True

state = State()

def parse_args() -> None:
    """Parse command-line arguments."""
    argparser = argparse.ArgumentParser(description='I want it all! -- image downloader')
    argparser.add_argument('--url', '-u', help='URL to download images from', required=False)
    argparser.add_argument('--output', '-o', help='Directory to save downloaded images', required=False)
    argparser.add_argument('--start', '-s', default = None, type=int, help='Start downloading from this image number', required=False)
    argparser.add_argument('--end', '-e', default=None, type=int, help='Stop downloading at this image number', required=False)
    argparser.add_argument('--username', '-n', help='username for authentication', required=False)
    argparser.add_argument('--password', '-p', help='password for authentication', required=False)
    argparser.add_argument('--allowed-spend-money', default='no', choices=['no', 'yes'], help="'yes' to allow activation of a purchased subscription. ⚠️ Attention: if you run the script simultaneously in multiple instances, use this option in only one of them.", required=False)
    override = argparser.parse_args()
    
    if override.output and override.output != '':
        state.config['local']['directory'] = override.output
    if override.username:
        state.config['remote']['username'] = override.username
    if override.password:
        state.config['remote']['password'] = override.password
    if override.url:
        state.remotePath = override.url
    if override.start:
        state.start = override.start
    if override.end:
        state.end = override.end
    if override.allowed_spend_money == 'yes':
        state.allowedSpendMoney = True
    return

def init() -> None:
    state.load_config(configFile)
    state.load_headers(headersFile)
    state.init_proxies()
    parse_args()
    

def get_images(imageList: list, dst: str, start: int, end: int) -> bool:
    total_images = len(imageList)
    if total_images == 0:
        print('No images found')
        return False
    if start > total_images:
        print("Start index is greater than the total number of images. Exiting!")
        return False
    if end > total_images:
        print(f'End index is greater than the total number of images. Downloading up to {max}')
        end = total_images

    if not os.path.exists(dst):
        os.makedirs(dst)
    else:
        print('Directory already exists. Skipping...')
        # return

    print(f'There are {total_images} images. Downloading from {start + 1} to {end}.')

    zeroMaskCount = len(str(len(imageList)))
    for i in range(start, end):
        imageURL = state.baseURL + state.viewerPath + imageList[i]
        request = fetch_file(imageURL)
        if not request:
            print(f"Download stopped at image {i}. To resume, run the script with -s {i+1}.")
            return False
        
        # Somebody should configure their Spring controller better instead of this: 'image/jpeg;charset=UTF-8'
        fileExtension = mimetypes.guess_extension(request.headers['Content-Type'].split(';')[0]) or '.bin' #type: ignore
        filename = dst + '/' + str(i+1).zfill(zeroMaskCount) + fileExtension
        with open(filename, 'wb') as file:    
            file.write(request.content) # type: ignore
        sys.stdout.write(f"\rCount: {i+1}")
        sys.stdout.flush()
        pause_time = random.uniform(0.3, 1)
        time.sleep(pause_time)
    
    print()
    return True



def fetch_file(url) -> requests.Response | None:
    """Fetch a file from the given URL."""

    # We'll try a few times:
    # A 302 response code can mean:
    #   1) We're not authenticated.
    #   2) We're not authorized to access the resource — we may need to purchase a subscription.
    #      After payment, a 402 error may appear when the subscription has expired.
    # A 402 code is possible if we were authenticated and the subscription was active, but then expired.
    # A 301 code is possible when we request a URL directly from the search results page without modification.

    retry = 4
    request = None
    while retry > 0:
        try:
            #If there is a redirect, it means our session is expired. We need to relogin
            request = state.session.get(url, headers=state.headers, proxies=state.proxies, allow_redirects=False)
            location = request.headers.get('Location') or ''
            if request.status_code == 200:
                break
            elif request.status_code == 301 and location.startswith('/lksrv/'):
                url = state.remoteHost+location #Got a valid redirection to the requested file
            elif request.status_code == 302:
                if not state.authenticate(location):
                    return
            elif request.status_code == 402:
                if state.activate_subscription():
                    break
            else:
                print(f'Error: {request.status_code} - {request.reason}')
                return
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
        retry-=1
    return request
    
def parse_index(htmlData: str) -> list:
    # 'curPage = GCWUMNXWYLKCMFWFBKXWUG&IOXKXWP.length;'
    jsArrayName = re.search(r'curPage = (\w+).length;', htmlData)
    if not jsArrayName:
        print("Couldn't parse the index")
        return []
    jsArray = re.search(r'var ' + jsArrayName.group(1) + ' = \\[(.*?)\\];', htmlData)
    if not jsArray:
        print("Couldn't parse the list")
        return []
    
    imgList = re.findall(r"'(.*?),?'", jsArray.group(1))
    return imgList

def main():
    init()
    print(f"Saving images to: {state.config['local']['directory']}")
    
    index = fetch_file(state.remotePath)
    if index is None:
        print('Failed to get index')
        return

    imageList = parse_index(index.content.decode('utf-8'))
    
    end = len(imageList)
    if state.end is not None and state.end >= state.start:
        end = state.end
    result = get_images(imageList, state.config['local']['directory'], state.start-1, end)
    
    if result and state.config['local']['destination'] > '' and os.path.exists(state.config['local']['destination']):
        subdirs = state.config['local']['directory'].split('/')
        lastDir = subdirs[-1] or subdirs[-2]
        try:
            os.replace(state.config['local']['directory'], state.config['local']['destination']+'/'+lastDir)
        except Exception as e:
            print(f"Error moving directory: {e}\nPlease move it manually.")

    print('Done!')

if __name__ == '__main__':
    main()
