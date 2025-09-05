import os
import requests
from datetime import datetime
import time
import base64

URL_REPOS_LIST = 'https://api.github.com/search/repositories?q=cosmic%20org%3Apop-os'
URL_FTL_LOOKUP = 'https://api.github.com/search/code?q=repo%3Apop-os%2F{repo}%20extension%3Aftl'
URL_FTL_COMMIT = 'https://api.github.com/repos/pop-os/{repo}/commits'

LOCALE_SRC = 'en'
LOCALE_DST = 'ru'

REQ_DELAY = 1
RETRY_DELAY = 5
MAX_RETRIES = 10

req_cnt = 0
req_sec = 0


def make_request(url, headers, params=None):
    global req_cnt, req_sec

    for r in range(MAX_RETRIES):
        req_sec += REQ_DELAY
        time.sleep(REQ_DELAY) # try to behave nice from the start :)

        print('.', end='', flush=True)
        req_cnt += 1
        res = requests.get(url, headers=headers, params=params)

        if res.status_code == 403: # GH sends too many requests error as 403, for some reason
            req_sec += RETRY_DELAY
            time.sleep(RETRY_DELAY)
        else:
            res.raise_for_status() # status code != 200 --> show error
            print(' ', end='', flush=True)
            return res

    print('\nAllowed max number of GitHub API request attemps exceeded!')
    exit(-1)

def get_ftl_text(url):
    res = make_request(
        url,
        headers={
            'Authorization': f'Bearer {a}'
        }
    )
    ftl_text_raw = res.json()

    ftl_text = base64.b64decode(ftl_text_raw['content']) # GH returns content as Base64
    ftl_text = ftl_text.decode('UTF-8') # convert from Unicode to UTF-8
    ftl_text = ftl_text.replace('\n\n', '\n') # remove empty lines
    if (ftl_text.endswith('\n')):
        ftl_text = ftl_text[:-1] # remove extra empty line at the end, if present

    return ftl_text

def get_ftl_date(repo, path):
    res = make_request(
        URL_FTL_COMMIT.format(repo=repo),
        headers={
            'Authorization': f'Bearer {a}'
        },
        params={
            'path': path, # get just the file we need
            'per_page': 1 # we only care about the latest commit
        }
    )
    ftl_date_raw = res.json()

    ftl_date = ftl_date_raw[0]['commit']['committer']['date'] # get commit date
    ftl_date = datetime.strptime(ftl_date, '%Y-%m-%dT%H:%M:%SZ') # parse it...
    ftl_date = ftl_date.timestamp() # ...and derive the timestamp!

    return ftl_date


if __name__ == "__main__":
    print(f'=== State of components\' translations as of {str(datetime.now()).split('.')[0]} ===')

    a = None
    if os.path.isfile('./a.txt'):
        a = open('./a.txt', 'r').read().strip()
    else:
        print('\nUnable to open GitHub API кеу file (a.txt) -- ПАПОЧКА ЗОЛ....')
        exit(-1)


    res = make_request(
        URL_REPOS_LIST,
        headers={
            'Authorization': f'Bearer {a}'
        },
        params={
            'per_page': 100
        }
    )

    repos_raw = res.json()
    repos = [repo['name'] for repo in repos_raw['items']]
    print(f'\nFound suitable repos: {len(repos)}')


    for repo in repos:
        print(f'\n{repo}', end='')

        ftls_page = 1 # pagination starts from 1st page, not 0th
        ftls_allitems = []

        while True:
            res = make_request(
                URL_FTL_LOOKUP.format(repo=repo),
                headers={
                    'Authorization': f'Bearer {a}'
                },
                params={
                    'per_page': 30, 'page': ftls_page
                }
            )

            ftls_raw = res.json()
            ftls_allitems.extend(ftls_raw['items'])

            if len(ftls_raw['items']) < 30:
                break # this means this page was the last
            else:
                ftls_page += 1 # go to next page

        # CASE 01 -- There is nothing to translate
        if (len(ftls_allitems) == 0):
            print('\n➖ No ftls found')
            continue


        ftls_src_meta = list(filter(lambda m: f'/{LOCALE_SRC}/' in m['path'], ftls_allitems))
        ftls_dst_meta = list(filter(lambda m: f'/{LOCALE_DST}/' in m['path'], ftls_allitems))
        names_src = {m['name'] for m in ftls_src_meta}
        names_dst = {m['name'] for m in ftls_dst_meta}

        for name in names_src:
            ftl_src_meta = next((m for m in ftls_src_meta if m['name'] == name), None)
            ftl_src_text = get_ftl_text(ftl_src_meta['url'])
            ftl_src_strs = ftl_src_text.count('\n') + 1

            if (name not in names_dst):
                # CASE 02 -- Target locale is missing completely
                print(f'\n❌ 0/{ftl_src_strs} (0%) -- {LOCALE_DST}/{name} does not exist in https://github.com/pop-os/{repo}')
                continue

            ftl_dst_meta = next((m for m in ftls_dst_meta if m['name'] == name), None)
            ftl_dst_text = get_ftl_text(ftl_dst_meta['url'])
            ftl_dst_strs = ftl_dst_text.count('\n') + 1

            # CASE 03 -- Amount of strings in target ftl file
            # doesn't match with amount of strings in source ftl file
            if (ftl_src_strs != ftl_dst_strs):
                print(
                    f'{"\n⏫ " if (abs(ftl_src_strs - ftl_dst_strs) >= 20) else "\n🔼 "}'
                    + f'{ftl_dst_strs}/{ftl_src_strs} '
                    + f'({int(ftl_dst_strs/ftl_src_strs*100)}%) -- {ftl_dst_meta["html_url"]}'
                )
                continue


            ftl_src_date = get_ftl_date(repo, ftl_src_meta['path'])
            ftl_dst_date = get_ftl_date(repo, ftl_dst_meta['path'])

            # CASE 04 -- No difference in amount of strings, but last
            # source ftl file is newer than last target ftl file
            if (ftl_src_date > ftl_dst_date):
                print(f'\n⬆️ Newer src ftl -- {ftl_dst_meta["html_url"]}')
                continue


            # Finally, CASE 05 -- Target ftl file is both up-to-date
            # and has the same amount of strings as source ftl file (Ура!)
            print(f'\n✅ {ftl_dst_strs}/{ftl_src_strs} (100%) -- {ftl_dst_meta["html_url"]}')


    print(f'\n=== Total requests: {req_cnt} ({req_sec} sec) | FTL_LOOKUP v1.1.0 (25-09-05) ===')
    exit(0)
