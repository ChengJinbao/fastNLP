r"""
本文件中的 **Pipe** 主要用于处理问答任务的数据。

"""

from copy import deepcopy

from .pipe import Pipe
from fastNLP.io.data_bundle import DataBundle
from ..loader.qa import CMRC2018Loader
from .utils import get_tokenizer
from fastNLP.core.dataset import DataSet
from fastNLP.core.vocabulary import Vocabulary

__all__ = ['CMRC2018BertPipe']


def _concat_clip(data_bundle, max_len, concat_field_name='raw_chars'):
    r"""
    处理data_bundle中的DataSet，将context与question按照character进行tokenize，然后使用[SEP]将两者连接起来。

    会新增field: context_len(int), raw_words(list[str]), target_start(int), target_end(int)其中target_start
    与target_end是与raw_chars等长的。其中target_start和target_end是前闭后闭的区间。

    :param DataBundle data_bundle: 类似["a", "b", "[SEP]", "c", ]
    :return:
    """
    tokenizer = get_tokenizer('cn-char', lang='cn')
    for name in list(data_bundle.datasets.keys()):
        ds = data_bundle.get_dataset(name)
        data_bundle.delete_dataset(name)
        new_ds = DataSet()
        for ins in ds:
            new_ins = deepcopy(ins)
            context = ins['context']
            question = ins['question']

            cnt_lst = tokenizer(context)
            q_lst = tokenizer(question)

            answer_start = -1

            if len(cnt_lst) + len(q_lst) + 3 > max_len:  # 预留开头的[CLS]和[SEP]和中间的[sep]
                if 'answer_starts' in ins and 'answers' in ins:
                    answer_start = int(ins['answer_starts'][0])
                    answer = ins['answers'][0]
                    answer_end = answer_start + len(answer)
                    if answer_end > max_len - 3 - len(q_lst):
                        span_start = answer_end + 3 + len(q_lst) - max_len
                        span_end = answer_end
                    else:
                        span_start = 0
                        span_end = max_len - 3 - len(q_lst)
                    cnt_lst = cnt_lst[span_start:span_end]
                    answer_start = int(ins['answer_starts'][0])
                    answer_start -= span_start
                    answer_end = answer_start + len(ins['answers'][0])
                else:
                    cnt_lst = cnt_lst[:max_len - len(q_lst) - 3]
            else:
                if 'answer_starts' in ins and 'answers' in ins:
                    answer_start = int(ins['answer_starts'][0])
                    answer_end = answer_start + len(ins['answers'][0])

            tokens = cnt_lst + ['[SEP]'] + q_lst
            new_ins['context_len'] = len(cnt_lst)
            new_ins[concat_field_name] = tokens

            if answer_start != -1:
                new_ins['target_start'] = answer_start
                new_ins['target_end'] = answer_end - 1

            new_ds.append(new_ins)
        data_bundle.set_dataset(new_ds, name)

    return data_bundle


class CMRC2018BertPipe(Pipe):
    r"""
    处理 **CMRC2018** 的数据，处理之后 :class:`~fastNLP.core.DataSet` 中新增的内容如下（原有的 field 仍然保留）：

    .. csv-table::
        :header: "context_len", "raw_chars",  "target_start", "target_end", "chars"
        
        492, "['范', '廷', '颂... ]", 30, 34, "[21, 25, ...]"
        491, "['范', '廷', '颂... ]", 41, 61, "[21, 25, ...]"
        ".", "...", "...","...", "..."

    ``raw_chars`` 列是 ``context`` 与 ``question`` 拼起来的结果（连接的地方加入了 ``[SEP]`` ）， ``chars`` 是转为
    index 的值， ``target_start`` 为答案开始的位置， ``target_end`` 为答案结束的位置（闭区间）； ``context_len``
    指示的是 ``chars`` 列中 context 的长度。

    :param max_len:
    """

    def __init__(self, max_len=510):
        super().__init__()
        self.max_len = max_len

    def process(self, data_bundle: DataBundle) -> DataBundle:
        r"""
        ``data_bunlde`` 中的 :class:`~fastNLP.core.DataSet` 应该包含 ``raw_words`` ：

        .. csv-table::
           :header: "title", "context", "question", "answers", "answer_starts", "id"

           "范廷颂", "范廷颂枢机（，），圣名保禄·若瑟（）...", "范廷颂是什么时候被任为主教的？", ["1963年"], ["30"], "TRAIN_186_QUERY_0"
           "范廷颂", "范廷颂枢机（，），圣名保禄·若瑟（）...", "1990年，范廷颂担任什么职务？", ["1990年被擢升为天..."], ["41"],"TRAIN_186_QUERY_1"
           "...", "...", "...","...", ".", "..."

        :param data_bundle:
        :return: 处理后的 ``data_bundle``
        """
        data_bundle = _concat_clip(data_bundle, max_len=self.max_len, concat_field_name='raw_chars')

        src_vocab = Vocabulary()
        src_vocab.from_dataset(*[ds for name, ds in data_bundle.iter_datasets() if 'train' in name],
                               field_name='raw_chars',
                               no_create_entry_dataset=[ds for name, ds in data_bundle.iter_datasets()
                                                        if 'train' not in name]
                               )
        src_vocab.index_dataset(*data_bundle.datasets.values(), field_name='raw_chars', new_field_name='chars')
        data_bundle.set_vocab(src_vocab, 'chars')

        return data_bundle

    def process_from_file(self, paths=None) -> DataBundle:
        r"""
        传入文件路径，生成处理好的 :class:`~fastNLP.io.DataBundle` 对象。``paths`` 支持的路径形式可以参考 :meth:`fastNLP.io.Loader.load`

        :param paths:
        :return:
        """
        data_bundle = CMRC2018Loader().load(paths)
        return self.process(data_bundle)
