#!/usr/bin/env python
import argparse
import json
import os
import re
import time
import warnings
from concurrent import futures
from contextlib import ContextDecorator
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

import requests


class ProgressInfo(ContextDecorator):

    def __init__(self,
                 start_info: str = "Starting",
                 finish_info: str = "Finished"):

        self.t0 = time.time()
        self.start_info = start_info
        self.finish_info = finish_info
        super().__init__()

    def __enter__(self):
        print(self.start_info.ljust(20), end="\t")
        return self

    def __exit__(self, *exc):
        elapse = (time.time() - self.t0) / 1000
        print(f'{ self.finish_info }\t 耗时:{ elapse :0.5f}s')
        return False


class WenKuClient:
    session = requests.Session()
    concurrency = 8

    @staticmethod
    def load_jsonp(content: Union[str, bytes]) -> Any:
        """parse jsonp"""
        if isinstance(content, bytes):
            content = content.decode("u8")

        # find the first '(' and the last ')' and extract the substr between them
        lindex = content.find('(')
        rindex = content.rindex(')')
        return json.loads(content[lindex + 1: rindex])

    @staticmethod
    def parse_doc_id(url: str) -> Optional[str]:
        """parse doc_id from url with regex"""

        pat = re.compile(r'([0-9a-f]{8,})')
        result = pat.findall(url)
        if result:
            return result[0]

    @classmethod
    @ProgressInfo("正在获取文档信息...")
    def get_doc_info(cls, doc_id: str) -> Dict[str, Any]:
        """get doc meta info describing the doc from api

        example url:
        https://wenku.baidu.com/api/doc/getdocinfo?doc_id=1a0992fe5e0e7cd184254b35eefdc8d377ee1453&callback=cb

        the response json like:
        ```json
            {
                "doc_id": "080f08af998fcc22bcd10d77",
                "docInfo": {
                    "docTitle": "doc title",
                },
                "mydoc": 0,
                "xz_top1": 0,
                "htmlBcs": false,
                "isHtml": true,
                "md5sum": "...",
                "bcsParam": [
                    {
                        "merge": "0-5863",
                        "zoom": "&png=0-0&jpg=0-0",
                        "page": 1
                    },

                ],
                "downloadToken": "...",
                "matchStatus": 1,
            }
        ```
        """
        url = 'https://wenku.baidu.com/api/doc/getdocinfo'
        params = {'callback': 'cb', 'doc_id': doc_id}
        content = requests.get(url, params=params).content
        return cls.load_jsonp(content)

    @classmethod
    def parse_image_urls(cls, doc_info: dict) -> List[str]:
        """parse image url from doc meta info

        `bcsParam` field describes image params for bcs(baidu cloud service)
        `md5sum` field describes sign params to fetch image

        the image url and params are described in `bcsParam` field
        """

        md5sum = doc_info['md5sum']
        doc_id = doc_info['doc_id']
        pat = re.compile(r'png=(\d+-\d+)&jpg=(\d+-\d+)')

        urls = []
        for param in doc_info['bcsParam']:
            img_fmt = 'jpg'

            zoom: str = param['zoom']
            res = pat.findall(zoom)

            if not res:
                continue

            png_range, jpg_range = res[0]

            # not image, when doc is in format of word or txt
            if jpg_range == '0-0' and png_range == '0-0':
                continue

            # png image
            if jpg_range == '0-0':
                img_fmt = 'png'
            url = f'https://wkretype.bdimg.com/retype/zoom/{doc_id}?o={ img_fmt }{ md5sum }{ zoom }'
            urls.append(url)
        return urls

    @classmethod
    def parse_doc_content(cls, raw: bytes) -> str:
        """parse text from doc info

        wenku describe every small fragments of word document with json
        """
        items = cls.load_jsonp(raw)['body']
        text = "".join([item['c'] for item in items if item['t'] == 'word'])
        return text

    @classmethod
    @ProgressInfo("正在获取文档文本...")
    def get_text(cls, doc_id: dict) -> str:
        """get text of doc_id"""
        url = f'https://wenku.baidu.com/view/{ doc_id }'
        html = cls.session.get(url).content.decode('gb2312')

        pat = re.compile(r'WkInfo\.htmlUrls\s=\s\'(.*\})', re.IGNORECASE)
        res = pat.findall(html)
        if not res:
            return ''

        json_text = res[0]
        json_text = json_text.replace(r"\x22", '"').replace(r'\\', '')
        doc: dict = json.loads(json_text)
        content_info: list = doc['json']
        urls = [item['pageLoadUrl'] for item in content_info]
        frags = []
        for data in cls.batch_fetch(urls):
            text = cls.parse_doc_content(data)
            frags.append(text)
        return "".join(frags)

    @classmethod
    @ProgressInfo(start_info="正在获取文档图片...")
    def get_images(cls, doc_info: dict) -> Tuple[str, bytes]:
        image_urls = cls.parse_image_urls(doc_info)
        results = cls.batch_fetch(image_urls)
        for idx, data in enumerate(results, 1):
            ext = 'jpg' if 'o=jpg' in image_urls[idx-1] else 'png'
            yield f'page-{ idx }.{ ext }', data

    @classmethod
    def batch_fetch(cls, urls: List[str]) -> Iterable[bytes]:
        """fetch content from batch urls concurrency and in order by ThreadPoolExecutor"""
        def get_content(url: str) -> bytes:
            return requests.get(url).content

        tasks = []
        with futures.ThreadPoolExecutor(max_workers=cls.concurrency) as executor:
            for url in urls:
                task = executor.submit(get_content, url)
                tasks.append(task)

            for task in tasks:
                yield task.result()

    @staticmethod
    def mkdir(dirname: str):
        try:
            os.mkdir(dirname)
        except Exception as e:  # noqa
            pass

    @classmethod
    def fetch(cls, url: str):

        doc_id = cls.parse_doc_id(url)
        if not doc_id:
            warnings.warn(f"Can not get doc_id from { url }")
            return

        doc_info = cls.get_doc_info(doc_id)

        title = doc_info['docInfo']['docTitle']
        cls.mkdir(title)

        for filename, data in cls.get_images(doc_info):
            with open(f"{title}/{filename}", 'wb') as f:
                f.write(data)

        with open(f'{title}/{ title }.txt', 'w') as f:
            f.write(cls.get_text(doc_id))
        print(f"文档下载到目录: { title }")


if __name__ == "__main__":

    description = '''Baidu Wenku Downloader. Usage: python wenku.py <url>'''
    cmd = argparse.ArgumentParser(description=description)
    cmd.add_argument("url", type=str)
    args = cmd.parse_args()
    WenKuClient.fetch(args.url)
