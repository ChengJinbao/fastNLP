
import unittest
from fastNLP.io.pipe.qa import CMRC2018BertPipe
from fastNLP.io.loader.qa import CMRC2018Loader


class CMRC2018PipeTest(unittest.TestCase):
    def test_process(self):
        data_bundle = CMRC2018Loader().load('tests/data_for_tests/io/cmrc/')
        pipe = CMRC2018BertPipe()
        data_bundle = pipe.process(data_bundle)

        for name, dataset in data_bundle.iter_datasets():
            for ins in dataset:
                if 'target_start' in ins:
                    #  抓到的答案是对应上的
                    start_index = ins['target_start']
                    end_index = ins['target_end']+1
                    extract_answer = ''.join(ins['raw_chars'][start_index:end_index])
                    self.assertEqual(extract_answer, ins['answers'][0])
                # 测试context_len是对的
                raw_chars = ins['raw_chars']
                expect_len = raw_chars.index('[SEP]')
                self.assertEqual(expect_len, ins['context_len'])
