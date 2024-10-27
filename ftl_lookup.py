import os
import requests
from datetime import datetime
import time
import base64

LOCALE_SRC = 'en'
LOCALE_DST = 'ru'
RQ_DELAY = 1
RETRY_DELAY = 5
MAX_RETRIES = 10


rq_cnt = 0
time_cnt = 0

def make_request(url, headers, params=None):
    global rq_cnt, time_cnt

    for r in range(MAX_RETRIES):
        time_cnt += RQ_DELAY
        time.sleep(RQ_DELAY) # Пробуем изначально вести себя хорошо и не превышать лимит запросов

        print('.', end='' , flush=True)
        rq_cnt += 1
        res = requests.get(url, headers=headers, params=params)

        if res.status_code == 403: # Превышение числа запросов GH шлёт именно под кодом 403
            time_cnt += RETRY_DELAY
            time.sleep(RETRY_DELAY)
        else:
            res.raise_for_status() # Код != 200 --> Выводим ошибку
            print(' ', end='', flush=True)
            return res

    print('\n=== Превышено макисмальное число попыток получения данных от GH API! ===')
    exit(-1)


print(f'=== Состояние компонентов перевода на {str(datetime.now())} ===')

a = None
if os.path.isfile('./a.txt'):
    a = open('./a.txt', 'r').read().split('\n')[0]
else:
    print('\nОстутствует файл ключа аутентификации a.txt (ПАПОЧКА ЗОЛ....)')
    exit(-1)


res = make_request(
    'https://api.github.com/search/repositories?q=cosmic%20org%3Apop-os',
    headers={
        'Authorization': f'Bearer {a}'
    },
    params={
        'per_page': 100
    }
)

repos_raw = res.json()
repos = [repo['name'] for repo in repos_raw['items']]
print(f'\nНайдено репозиториев: {len(repos)}')


for repo in repos:
    print(f'\n{repo}')

    ftls_allitems = []
    ftls_page = 1
    while True:
        
        
        res = make_request(
            f'https://api.github.com/search/code?q=repo%3Apop-os%2F{repo}%20extension%3Aftl',
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
            break # Достигнут конец пагинации, записаны все ftl-файлы
        else:
            ftls_page += 1 # Переходим на след. страницу
    
    # Случай 1 -- В компоненте нечего переводить
    if (len(ftls_allitems) == 0):
        print('➖')
        continue


    ftls_src_meta = list(filter(lambda m: f'/{LOCALE_SRC}/' in m['path'], ftls_allitems))
    ftls_dst_meta = list(filter(lambda m: f'/{LOCALE_DST}/' in m['path'], ftls_allitems))

    ftl_src_names = set([ftls_src_meta[i]['name'] for i in range(len(ftls_src_meta))])
    ftl_dst_names = set([ftls_dst_meta[i]['name'] for i in range(len(ftls_dst_meta))])
    flt_names_difference = ftl_src_names - ftl_dst_names

    # Случай 2 -- Требуемая локаль компонента отсутствует полностью
    for name in flt_names_difference:
        print(f'⭕ {LOCALE_DST}/{name} не существует в https://github.com/pop-os/{repo}')


    for ftl_src_meta, ftl_dst_meta in zip(ftls_src_meta, ftls_dst_meta):
        res = make_request(
            ftl_src_meta['url'],
            headers={
                'Authorization': f'Bearer {a}'
            }
        )

        ftl_src_raw = res.json()
        ftl_src = base64.b64decode(ftl_src_raw['content']) # GH отправляет контент в виде base64
        ftl_src = ftl_src.decode('UTF-8') # Переводим из Unicode в UTF-8
        ftl_src = ftl_src.replace('\n\n', '\n') # Удаляем пустые строки
        if (ftl_src.endswith('\n')):
            ftl_src = ftl_src[:-2] # Удаляем перенос строки из конца

        res = make_request(
            ftl_dst_meta['url'],
            headers={
                'Authorization': f'Bearer {a}'
            }
        )

        ftl_dst_raw = res.json()
        ftl_dst = base64.b64decode(ftl_dst_raw['content']) # GH отправляет контент в виде base64
        ftl_dst = ftl_dst.decode('UTF-8') # Переводим из Unicode в UTF-8
        ftl_dst = ftl_dst.replace('\n\n', '\n') # Удаляем пустые строки
        if (ftl_dst.endswith('\n')):
            ftl_dst = ftl_dst[:-2] # Удаляем перенос строки из конца

        ftl_src_lines = ftl_src.count('\n')
        ftl_dst_lines = ftl_dst.count('\n')

        # Случай 3 -- Число строк в требуемой локали
        # не соответствует числу строк в источнике
        if (ftl_src_lines != ftl_dst_lines):
            if (abs(ftl_src_lines - ftl_dst_lines) >= 20):
                print(f'⏫ https://github.com/pop-os/{repo}/{ftl_dst_meta["path"]}')
            else:
                print(f'🔼 https://github.com/pop-os/{repo}/{ftl_dst_meta["path"]}')
            continue


        res = make_request(
            f'https://api.github.com/repos/pop-os/{repo}/commits',
            headers={
                'Authorization': f'Bearer {a}'
            },
            params={
                'path': ftl_src_raw['path'], # Чтобы получить только историю этого файла
                'per_page': 1 # Чтобы получить только последний коммит
            }
        )

        ftl_src_date_raw = res.json()
        ftl_src_date = ftl_src_date_raw[0]['commit']['committer']['date'] # Достаём время коммита
        ftl_src_date = datetime.strptime(ftl_src_date, '%Y-%m-%dT%H:%M:%SZ') # Парсим время...
        ftl_src_date = ftl_src_date.timestamp() # ...и получаем таймштамп!

        res = make_request(
            f'https://api.github.com/repos/pop-os/{repo}/commits',
            headers={
                'Authorization': f'Bearer {a}'
            },
            params={
                'path': ftl_dst_raw['path'], # Чтобы получить только историю этого файла
                'per_page': 1 # Чтобы получить только последний коммит
            }
        )

        ftl_dst_date_raw = res.json()
        ftl_dst_date = ftl_dst_date_raw[0]['commit']['committer']['date'] # Достаём время коммита
        ftl_dst_date = datetime.strptime(ftl_dst_date, '%Y-%m-%dT%H:%M:%SZ') # Парсим время...
        ftl_dst_date = ftl_dst_date.timestamp() # ...и получаем таймштамп!

        # Случай 4 -- Дата посл. коммита источника более
        # поздняя, чем дата посл. коммита требуемой локали
        if (ftl_src_date > ftl_dst_date):
            print(f'⬆️ https://github.com/pop-os/{repo}/{ftl_dst_meta["path"]}')
            continue


        # Наконец, случай 5 -- Перевод ftl-файла актуален
        # и содержит совпадающее количество строк (ура!)
        print(f'✅ https://github.com/pop-os/{repo}/{ftl_dst_meta["path"]}')


print(f'\n=== Итоговое число запросов: {rq_cnt} ({time_cnt} сек.) | FTL_LOOKUP v1.0.0 (24-10-28) ===')
exit(0)
