#!/usr/bin/env python
import argparse
from enum import Flag
import json
import re
import time
import warnings
from pathlib import Path
from concurrent import futures
from contextlib import ContextDecorator
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

import requests


class ProgressInfo(ContextDecorator):
    start_info: str
    finish_info: str
    error_info: str

    def __init__(
        self,
        start_info: str = "Starting",
        finish_info: str = "Finished",
        error_info: str = "Failed",
    ):

        self.t0 = time.time()
        self.start_info = start_info
        self.finish_info = finish_info
        self.error_info = error_info
        super().__init__()

    def __enter__(self):
        print(self.start_info.ljust(20), end="\t")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        elapse = (time.time() - self.t0) / 1000
        if exc_value:
            print(f"{ self.error_info.ljust(10) } 耗时:{ elapse :0.5f}s\t原因:{ exc_value}")
            return True
        print(f"{ self.finish_info.ljust(10) } 耗时:{ elapse :0.5f}s")
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
        lindex = content.find("(")
        rindex = content.rindex(")")
        return json.loads(content[lindex + 1 : rindex])

    @staticmethod
    def parse_doc_id(url: str) -> Optional[str]:
        """parse doc_id from url with regex"""

        pat = re.compile(r"([0-9a-f]{8,})")
        result = pat.findall(url)
        if result:
            return result[0]

    @classmethod
    @ProgressInfo("正在获取文档信息...")
    def get_doc_info(cls, doc_id: str) -> Dict[str, Any]:
        """get doc meta info from api
        it contains detail meta info of the document
        example url:
        https://wenku.baidu.com/api/doc/getdocinfo?doc_id=1a0992fe5e0e7cd184254b35eefdc8d377ee1453&callback=cb

        the response json like below
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
        url = "https://wenku.baidu.com/api/doc/getdocinfo"
        params = {"callback": "cb", "doc_id": doc_id}
        content = requests.get(url, params=params).content
        return cls.load_jsonp(content)

    @classmethod
    def parse_image_urls(cls, doc_info: dict) -> List[str]:
        """parse image urls from doc meta info

        we need 'bcsParam' and 'md5sum' from doc_info to form image url
        """

        md5sum = doc_info["md5sum"]
        doc_id = doc_info["doc_id"]
        pat = re.compile(r"png=(\d+-\d+)&jpg=(\d+-\d+)")

        urls = []
        for param in doc_info["bcsParam"]:
            img_fmt = "jpg"

            zoom: str = param["zoom"]
            res = pat.findall(zoom)

            if not res:
                continue

            png_range, jpg_range = res[0]

            # when doc is in format of word or txt, it has no images
            if jpg_range == "0-0" and png_range == "0-0":
                continue

            # png image
            if jpg_range == "0-0":
                img_fmt = "png"
            url = f"https://wkretype.bdimg.com/retype/zoom/{doc_id}?o={ img_fmt }{ md5sum }{ zoom }"
            urls.append(url)
        return urls

    @classmethod
    def parse_doc_content(cls, raw: bytes) -> str:
        """parse text from doc info"""
        items = cls.load_jsonp(raw)["body"]
        last_y = None
        text = ""
        for item in items:
            if not item['t'] == "word":
                continue
            text += item['c']
            y = item['p']['y']
            if last_y is not None and abs(y - last_y) > 1:
                text += "\n"
            last_y = y
        return text

    @classmethod
    @ProgressInfo("正在获取文档文本...")
    def get_text(cls, doc_id: dict) -> str:
        """get text of doc_id"""
        url = f"https://wenku.baidu.com/view/{ doc_id }"
        html = cls.session.get(url).text
        pat = re.compile(r"var pageData = (\{.*\})")
        res = pat.findall(html)
        if not res:
            raise ValueError("无法解析页面")

        page_data = json.loads(res[0])
        html_url_content = page_data["readerInfo2019"]["htmlUrls"]
        html_urls = json.loads(html_url_content)
        if isinstance(html_urls, list):
            raise ValueError("非文本类型文档")

        url_infos = html_urls["json"]
        urls = [info["pageLoadUrl"] for info in url_infos]
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
            ext = "jpg" if "o=jpg" in image_urls[idx - 1] else "png"
            yield f"page-{ idx }.{ ext }", data

    @classmethod
    def batch_fetch(cls, urls: List[str]) -> Iterable[bytes]:
        """fetch content from batch urls concurrently and in order by ThreadPoolExecutor"""

        def get_content(url: str) -> bytes:
            c = requests.get(url).content
            return c

        tasks = []
        with futures.ThreadPoolExecutor(max_workers=cls.concurrency) as executor:
            for url in urls:
                task = executor.submit(get_content, url)
                tasks.append(task)

            for task in tasks:
                yield task.result()

    @staticmethod
    def mkdir(dirname: str) -> str:

        p = Path(dirname)
        p.mkdir(exist_ok=True)
        return p.absolute()

    @classmethod
    def fetch(cls, url: str):

        doc_id = cls.parse_doc_id(url)
        if not doc_id:
            warnings.warn(f"Can not get doc_id from { url }")
            return

        doc_info = cls.get_doc_info(doc_id)

        title = doc_info["docInfo"]["docTitle"]
        dirpath = cls.mkdir(title)

        for filename, data in cls.get_images(doc_info):
            with open(f"{title}/{filename}", "wb") as f:
                f.write(data)

        text = cls.get_text(doc_id)
        if text is None:
            warnings.warn("无文本信息")
            return

        with open(f"{title}/{ title }.txt", "w") as f:
            f.write(text)
        print(f"文档下载到目录: { dirpath }")


if __name__ == "__main__":

    description = """Baidu Wenku Downloader. Usage: wenku.py <url>"""
    cmd = argparse.ArgumentParser(description=description)
    cmd.add_argument("url", type=str)
    args = cmd.parse_args()
    WenKuClient.fetch(args.url)
