import unittest
from wenku import WenKuClient


class TestWenkuClient(unittest.TestCase):

    def test_parse_doc_id(self):
        """parse doc_id from url"""
        url = 'https://wenku.baidu.com/view/babe068418e8b8f67c1cfad6195f312b3169ebf9.html'
        doc_id = WenKuClient.parse_doc_id(url)
        self.assertEqual(doc_id, "babe068418e8b8f67c1cfad6195f312b3169ebf9")

        url = '/764658986845968abdbbd/'
        doc_id = WenKuClient.parse_doc_id(url)
        self.assertEqual(doc_id, '764658986845968abdbbd')

    def test_load_jsonp(self):
        content = '''cb({"a": 1, "b": 2})'''

        data = WenKuClient.load_jsonp(content)
        self.assertEqual(data['a'], 1)

        content = b'''/**/callback({"a": 1})/*comment*/'''
        data = WenKuClient.load_jsonp(content)
        self.assertEqual(data['a'], 1)


if __name__ == "__main__":
    unittest.main()
