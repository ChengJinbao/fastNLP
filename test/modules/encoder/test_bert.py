import unittest


from fastNLP.modules import BertTokenizer


class TestBertTokenizer(unittest.TestCase):
    def test_run(self):
        # 测试支持的两种encode方式
        tokenizer = BertTokenizer.from_pretrained('test/data_for_tests/embedding/small_bert')

        tokens1 = tokenizer.encode("This is a demo")
        tokens2 = tokenizer.encode("This is a demo")
        tokens3 = tokenizer.encode("This is a demo".split())
        tokens4 = tokenizer.encode("This is a demo".split())

        self.assertEqual(len(tokens1)-2, len(tokens2))
        self.assertEqual(len(tokens3)-2, len(tokens4))

        self.assertEqual(tokens1[0], tokenizer.cls_index)
        self.assertEqual(tokens1[-1], tokenizer.sep_index)



