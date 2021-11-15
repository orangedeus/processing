import requests
import argparse

UPLOAD_URL = 'http://18.136.217.164:3001/upload'
INSERT_URL = 'http://18.136.217.164:3001/stops/insert'
INSERT2_URL = 'http://18.136.217.164:3001/stops/insert_screened'

def upload(filename):
    with open(filename, 'rb') as f:
        file = {'upload_file': f}
        r = requests.post(UPLOAD_URL, files=file)
        return(r)

def insert(x, y, people, url, duration, route, batch, source_file):
    data = {
        'location': {
            'x': x,
            'y': y
        },
        'people': people,
        'url': url,
        'duration': duration,
        'route': route,
        'batch': batch,
        'source_file': source_file
    }
    r = requests.post(INSERT_URL, json=data)
    return r

def insert2(x, y, people):
    data = {
        'location': {
            'x': x,
            'y': y
        },
        'people': people
    }
    r = requests.post(INSERT2_URL, json=data)
    return r

def main(filename):
    i_res = insert(14.647138888888888, 121.06059444444445, 23, filename)
    u_res = upload(filename)
    print(i_res)
    print(u_res)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-V', '--video', required=True, default='uploaded.mp4')
    args = parser.parse_args()
    try:
        main(args.video)
    except Exception as e:
        print('[-] Directory may not be accessible, or: %s' % e)