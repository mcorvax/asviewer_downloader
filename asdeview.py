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
        self.loginURL = self.remoteHost + '/auth'
        self.remotePath = ''
        self.start = 1
        self.end = None 
        self.token = None
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
            self.loginURL = self.config['remote']['loginUrl']

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
        if loc and loc.startswith(state.remoteHost+'/private/subscription'):
            return activate_subscription()
        
        if loc and not loc.index(state.loginURL):
            print(f"Got a new redirect: {loc}. Don't know what to do... ") 
            return False
        
        print('Trying authenticate...')
        if not ('remote' in state.config
                and 'username' in state.config['remote'] and state.config['remote']['username'] > ''
                and 'username' in state.config['remote'] and state.config['remote']['username'] >''):
            return False
        headers = state.headers
        headers['Content-Type'] = 'application/json'
        headers['Referer'] = state.config['remote']['loginURL']
        headers['Accept'] = 'application/json, text/plain, */*'
        
        state.session.cookies.set('auth.strategy', 'local')
        state.session.cookies.set('auth._token.local', 'false')
        state.session.cookies.set('auth._token_expiration.local', 'false')
        state.session.cookies.set('auth.redirect', '/private/me')

        payload = {
            'username': state.config['remote']['username'],
            'password': state.config['remote']['password']
        }
        try:
            response = state.session.get(state.loginURL, headers=headers, proxies=state.proxies, json=payload)
            if response.status_code != 200:
                print(f"Authentication failed: {response.status_code} - {response.reason}")
                return False
        except requests.RequestException as e:
            print(f"Error during authentication: {e}")
            return False
        
        state.token = response.json()['token']
        state.session.cookies.set("auth._token.local", f"Bearer {state.token}")
        state.headers['Authorization'] = f"Bearer {state.token}"
        print('Authenticated!')
        return True

state = State()

def parse_args() -> None:
    """Parse command-line arguments."""
    argparser = argparse.ArgumentParser(description='I want it all! -- image downloader')
    argparser.add_argument('--url', '-u', help='URL to download images from', required=False)
    argparser.add_argument('--output', '-o', help='Output directory', required=False)
    argparser.add_argument('--start', '-s', default = None, type=int, help='the number of the first image to download', required=False)
    argparser.add_argument('--end', '-e', default=None, type=int, help='the number of the last image to download', required=False)
    argparser.add_argument('--username', '-n', help='username for authentication', required=False)
    argparser.add_argument('--password', '-p', help='password for authentication', required=False)
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

def init() -> None:
    state.load_config(configFile)
    state.load_headers(headersFile)
    state.init_proxies()
    parse_args()
    

def get_images(imageList: list, dst: str, start: int, end: int) -> bool:
    max = len(imageList)
    if max == 0:
        print('No images found')
        return False
    if start > max:
        print("Start index is greater than the number of images. Exit!")
        return False
    if end > max:
        print("End index is greater than the number of images. Downloading till {max}")
        end = max

    if not os.path.exists(dst):
        os.makedirs(dst)
    else:
        print('Directory already exists. Skip...')
        # return

    print('There are ', max, 'images. Downloading from', start+1, 'to', end)

    zeroMaskCount = len(str(len(imageList)))
    for i in range(start, end):
        imageURL = state.baseURL + state.viewerPath + imageList[i]
        request = fetch_file(imageURL)
        
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

def activate_subscription() -> bool:
    #TODO: if there is prepaid subscriptions ...
    print('Subscription expired. Please activate a new one mannualy.')
    return False


def fetch_file(url) -> requests.Response | None:
    """Fetch a file from the given URL."""

    #We'll try a few two times: 
    # An answer with 302 error code can mean: 
    #    1) we're not authenticated
    #    2) we're not authorized to get a resource = we need to buy subscription. After payment we'll get 402 when time is expired
    # Code 402 i possible when we were authenticated and Subscription was active, but then expired

    retry = 3
    request = None
    while retry > 0:
        try:
            #If there is a redirect, it means our session is expired. We need to relogin
            request = state.session.get(url, headers=state.headers, proxies=state.proxies, allow_redirects=False)
            if request.status_code == 200:
                break
            elif request.status_code == 302:
                if not state.authenticate(request.headers.get('Location')):
                    return
            elif request.status_code == 402:
                if not activate_subscription():
                    return
            else:
                print('Error:', request.status_code, request.reason)
                return
        except requests.exceptions.RequestException as e:
            print('Request failed:', e)
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
    print('Output directory:', state.config['local']['directory'])

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
            print('Error moving directory:', e)
            print ('Move it manualy')

    print('Done!')

if __name__ == '__main__':
    main()
