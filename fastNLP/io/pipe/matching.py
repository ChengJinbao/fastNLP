__all__ = [
    "MatchingBertPipe",
    "RTEBertPipe",
    "SNLIBertPipe",
    "QuoraBertPipe",
    "QNLIBertPipe",
    "MNLIBertPipe",
    "CNXNLIBertPipe",
    "BQCorpusBertPipe",
    "LCQMCBertPipe",
    "MatchingPipe",
    "RTEPipe",
    "SNLIPipe",
    "QuoraPipe",
    "QNLIPipe",
    "MNLIPipe",
    "LCQMCPipe",
    "CNXNLIPipe",
    "BQCorpusPipe",
    "RenamePipe",
    "GranularizePipe",
    "TruncateBertPipe",
]
from functools import partial

from fastNLP.core.log import logger
from .pipe import Pipe
from .utils import get_tokenizer
from ..data_bundle import DataBundle
from ..loader.matching import SNLILoader, MNLILoader, QNLILoader, RTELoader, QuoraLoader, BQCorpusLoader, CNXNLILoader, \
    LCQMCLoader
# from ...core.const import Const
from ...core.vocabulary import Vocabulary


class MatchingBertPipe(Pipe):
    r"""
    **Matching** 任务的 Bert pipe ，处理之后 :class:`~fastNLP.core.DataSet` 中的内容如下：

    .. csv-table::
       :header: "raw_words1", "raw_words2", "target", "words", "seq_len"

       "The new rights are...", "Everyone really likes..", 1,  "[2, 3, 4, 5, ...]", 10
       "This site includes a...", "The Government Executive...", 0, "[11, 12, 13,...]", 5
       "...", "...", ., "[...]", .

    ``words`` 列是将 ``raw_words1`` （即 ``premise`` ）， ``raw_words2`` （即 ``hypothesis`` ）使用 ``[SEP]``
    链接起来转换为 index 的。``words`` 列被设置为 input， ``target`` 列被设置为 target 和 input （设置为 input 以
    方便在 :func:`forward` 函数中计算 loss，如果不在也不影响， **fastNLP** 将根据 :func:`forward` 函数的形参名进行
    传参）。

    :param lower: 是否对输入进行小写化。
    :param tokenizer: 使用哪种 tokenize 方式将数据切成单词。支持 ``['spacy', 'raw']`` 。``'raw'`` 表示使用空格作为切分，``'spacy'`` 则使用 :mod:`spacy` 库进行分词。
    :param num_proc: 处理数据时使用的进程数目。
    """
    
    def __init__(self, lower=False, tokenizer: str = 'raw', num_proc: int = 0):
        super().__init__()
        
        self.lower = bool(lower)
        self.tokenizer = get_tokenizer(tokenize_method=tokenizer)
        self.num_proc = num_proc
    
    def _tokenize(self, data_bundle, field_names, new_field_names):
        r"""

        :param DataBundle data_bundle: DataBundle.
        :param list field_names: List[str], 需要tokenize的field名称
        :param list new_field_names: List[str], tokenize之后field的名称，与field_names一一对应。
        :return: 输入的DataBundle对象
        """
        for name, dataset in data_bundle.iter_datasets():
            for field_name, new_field_name in zip(field_names, new_field_names):
                dataset.apply_field(self.tokenizer, field_name=field_name, new_field_name=new_field_name, num_proc=self.num_proc)
        return data_bundle
    
    def process(self, data_bundle: DataBundle):
        r"""
        ``data_bunlde`` 中的 :class:`~fastNLP.core.DataSet` 应该具备以下结构：

        .. csv-table::
            :header: "raw_words1", "raw_words2", "target"

            "Dana Reeve, the widow of the actor...", "Christopher Reeve had an...", "not_entailment"
            "...","..."

        :param data_bundle:
        :return: 处理后的 ``data_bundle``
        """
        for dataset in data_bundle.datasets.values():
            if dataset.has_field('target'):
                dataset.drop(lambda x: x['target'] == '-')
        
        for name, dataset in data_bundle.datasets.items():
            dataset.copy_field('raw_words1', 'words1', )
            dataset.copy_field('raw_words2', 'words2', )
        
        if self.lower:
            for name, dataset in data_bundle.datasets.items():
                dataset['words1'].lower()
                dataset['words2'].lower()
        
        data_bundle = self._tokenize(data_bundle, ['words1', 'words2'],
                                     ['words1', 'words2'])
        
        # concat两个words
        def concat(ins):
            words0 = ins['words1']
            words1 = ins['words2']
            words = words0 + ['[SEP]'] + words1
            return words
        
        for name, dataset in data_bundle.iter_datasets():
            dataset.apply(concat, new_field_name='words', num_proc=self.num_proc)
            dataset.delete_field('words1')
            dataset.delete_field('words2')
        
        word_vocab = Vocabulary()
        word_vocab.from_dataset(*[dataset for name, dataset in data_bundle.datasets.items() if 'train' in name],
                                field_name='words',
                                no_create_entry_dataset=[dataset for name, dataset in data_bundle.datasets.items() if
                                                         'train' not in name])
        word_vocab.index_dataset(*data_bundle.datasets.values(), field_name='words')
        
        target_vocab = Vocabulary(padding=None, unknown=None)
        target_vocab.from_dataset(*[ds for name, ds in data_bundle.iter_datasets() if 'train' in name],
                                  field_name='target',
                                  no_create_entry_dataset=[ds for name, ds in data_bundle.iter_datasets()
                                                           if ('train' not in name) and (ds.has_field('target'))]
                                  )
        if len(target_vocab._no_create_word) > 0:
            warn_msg = f"There are {len(target_vocab._no_create_word)} target labels" \
                       f" in {[name for name in data_bundle.datasets.keys() if 'train' not in name]} " \
                       f"data set but not in train data set!."
            logger.warning(warn_msg)
            print(warn_msg)
        
        has_target_datasets = [dataset for name, dataset in data_bundle.datasets.items() if
                               dataset.has_field('target')]
        target_vocab.index_dataset(*has_target_datasets, field_name='target')
        
        data_bundle.set_vocab(word_vocab, 'words')
        data_bundle.set_vocab(target_vocab, 'target')

        for name, dataset in data_bundle.iter_datasets():
            dataset.add_seq_len('words')

        return data_bundle


class RTEBertPipe(MatchingBertPipe):
    """
    处理 **RTE** 数据。

    :param lower: 是否对输入进行小写化。
    :param tokenizer: 使用哪种 tokenize 方式将数据切成单词。支持 ``['spacy', 'raw']`` 。``'raw'`` 表示使用空格作为切分，``'spacy'`` 则使用 :mod:`spacy` 库进行分词。
    :param num_proc: 处理数据时使用的进程数目。
    """
    def process_from_file(self, paths=None):
        r"""
        传入文件路径，生成处理好的 :class:`~fastNLP.io.DataBundle` 对象。``paths`` 支持的路径形式可以参考 :meth:`fastNLP.io.Loader.load`

        :param paths:
        :return:
        """
        data_bundle = RTELoader().load(paths)
        return self.process(data_bundle)


class SNLIBertPipe(MatchingBertPipe):
    """
    处理 **SNLI** 数据。

    :param lower: 是否对输入进行小写化。
    :param tokenizer: 使用哪种 tokenize 方式将数据切成单词。支持 ``['spacy', 'raw']`` 。``'raw'`` 表示使用空格作为切分，``'spacy'`` 则使用 :mod:`spacy` 库进行分词。
    :param num_proc: 处理数据时使用的进程数目。
    """
    def process_from_file(self, paths=None):
        r"""
        传入文件路径，生成处理好的 :class:`~fastNLP.io.DataBundle` 对象。``paths`` 支持的路径形式可以参考 :meth:`fastNLP.io.Loader.load`

        :param paths:
        :return:
        """
        data_bundle = SNLILoader().load(paths)
        return self.process(data_bundle)


class QuoraBertPipe(MatchingBertPipe):
    """
    处理 **Quora** 数据。

    :param lower: 是否对输入进行小写化。
    :param tokenizer: 使用哪种 tokenize 方式将数据切成单词。支持 ``['spacy', 'raw']`` 。``'raw'`` 表示使用空格作为切分，``'spacy'`` 则使用 :mod:`spacy` 库进行分词。
    :param num_proc: 处理数据时使用的进程数目。
    """
    def process_from_file(self, paths):
        r"""
        传入文件路径，生成处理好的 :class:`~fastNLP.io.DataBundle` 对象。``paths`` 支持的路径形式可以参考 :meth:`fastNLP.io.Loader.load`

        :param paths:
        :return:
        """
        data_bundle = QuoraLoader().load(paths)
        return self.process(data_bundle)


class QNLIBertPipe(MatchingBertPipe):
    """
    处理 **QNNLI** 数据。

    :param lower: 是否对输入进行小写化。
    :param tokenizer: 使用哪种 tokenize 方式将数据切成单词。支持 ``['spacy', 'raw']`` 。``'raw'`` 表示使用空格作为切分，``'spacy'`` 则使用 :mod:`spacy` 库进行分词。
    :param num_proc: 处理数据时使用的进程数目。
    """
    def process_from_file(self, paths=None):
        r"""
        传入文件路径，生成处理好的 :class:`~fastNLP.io.DataBundle` 对象。``paths`` 支持的路径形式可以参考 :meth:`fastNLP.io.Loader.load`

        :param paths:
        :return:
        """
        data_bundle = QNLILoader().load(paths)
        return self.process(data_bundle)


class MNLIBertPipe(MatchingBertPipe):
    """
    处理 **MNLI** 数据。

    :param lower: 是否对输入进行小写化。
    :param tokenizer: 使用哪种 tokenize 方式将数据切成单词。支持 ``['spacy', 'raw']`` 。``'raw'`` 表示使用空格作为切分，``'spacy'`` 则使用 :mod:`spacy` 库进行分词。
    :param num_proc: 处理数据时使用的进程数目。
    """
    def process_from_file(self, paths=None):
        r"""
        传入文件路径，生成处理好的 :class:`~fastNLP.io.DataBundle` 对象。``paths`` 支持的路径形式可以参考 :meth:`fastNLP.io.Loader.load`

        :param paths:
        :return:
        """
        data_bundle = MNLILoader().load(paths)
        return self.process(data_bundle)


class MatchingPipe(Pipe):
    r"""
    **Matching** 任务的 Pipe，处理之后 :class:`~fastNLP.core.DataSet` 中的内容如下：

    .. csv-table::
       :header: "raw_words1", "raw_words2", "target", "words1", "words2", "seq_len1", "seq_len2"

       "The new rights are...", "Everyone really likes..", 1,  "[2, 3, 4, 5, ...]", "[10, 20, 6]", 10, 13
       "This site includes a...", "The Government Executive...", 0, "[11, 12, 13,...]", "[2, 7, ...]", 6, 7
       "...", "...", ., "[...]", "[...]", ., .

    ``words1`` 是 ``premise`` ，``words2`` 是 ``hypothesis`` 。其中 ``words1`` , ``words2`` , ``seq_len1``, ``seq_len2``
    被设置为 input； ``target`` 列被设置为 target 和 input （设置为 input 以
    方便在 :func:`forward` 函数中计算 loss，如果不在也不影响， **fastNLP** 将根据 :func:`forward` 函数的形参名进行
    传参）。

    :param lower: 是否对输入进行小写化。
    :param tokenizer: 使用哪种 tokenize 方式将数据切成单词。支持 ``['spacy', 'raw']`` 。``'raw'`` 表示使用空格作为切分，``'spacy'`` 则使用 :mod:`spacy` 库进行分词。
    :param num_proc: 处理数据时使用的进程数目。
    """
    
    def __init__(self, lower=False, tokenizer: str = 'raw', num_proc: int = 0):
        r"""
        
        :param bool lower: 是否将所有raw_words转为小写。
        :param str tokenizer: 将原始数据tokenize的方式。支持spacy, raw. spacy是使用spacy切分，raw就是用空格切分。
        """
        super().__init__()
        
        self.lower = bool(lower)
        self.tokenizer = get_tokenizer(tokenize_method=tokenizer)
        self.num_proc = num_proc
    
    def _tokenize(self, data_bundle, field_names, new_field_names):
        r"""

        :param ~fastNLP.DataBundle data_bundle: DataBundle.
        :param list field_names: List[str], 需要tokenize的field名称
        :param list new_field_names: List[str], tokenize之后field的名称，与field_names一一对应。
        :return: 输入的DataBundle对象
        """
        for name, dataset in data_bundle.iter_datasets():
            for field_name, new_field_name in zip(field_names, new_field_names):
                dataset.apply_field(self.tokenizer, field_name=field_name, new_field_name=new_field_name, num_proc=self.num_proc)
        return data_bundle
    
    def process(self, data_bundle: DataBundle):
        r"""
        ``data_bunlde`` 中的 :class:`~fastNLP.core.DataSet` 应该具备以下结构，可以没有 ``target`` 列：

        .. csv-table::
           :header: "raw_words1", "raw_words2", "target"

           "The new rights are...", "Everyone really likes..", "entailment"
           "This site includes a...", "The Government Executive...", "not_entailment"
           "...", "..."

        :param data_bundle:
        :return: 处理后的 ``data_bundle``
        """
        data_bundle = self._tokenize(data_bundle, ['raw_words1', 'raw_words2'],
                                     ['words1', 'words2'])
        
        for dataset in data_bundle.datasets.values():
            if dataset.has_field('target'):
                dataset.drop(lambda x: x['target'] == '-')
        
        if self.lower:
            for name, dataset in data_bundle.datasets.items():
                dataset['words1'].lower()
                dataset['words2'].lower()
        
        word_vocab = Vocabulary()
        word_vocab.from_dataset(*[dataset for name, dataset in data_bundle.datasets.items() if 'train' in name],
                                field_name=['words1', 'words2'],
                                no_create_entry_dataset=[dataset for name, dataset in data_bundle.datasets.items() if
                                                         'train' not in name])
        word_vocab.index_dataset(*data_bundle.datasets.values(), field_name=['words1', 'words2'])
        
        target_vocab = Vocabulary(padding=None, unknown=None)
        target_vocab.from_dataset(*[ds for name, ds in data_bundle.iter_datasets() if 'train' in name],
                                  field_name='target',
                                  no_create_entry_dataset=[ds for name, ds in data_bundle.iter_datasets()
                                                           if ('train' not in name) and (ds.has_field('target'))]
                                  )
        if len(target_vocab._no_create_word) > 0:
            warn_msg = f"There are {len(target_vocab._no_create_word)} target labels" \
                       f" in {[name for name in data_bundle.datasets.keys() if 'train' not in name]} " \
                       f"data set but not in train data set!."
            logger.warning(warn_msg)
            print(warn_msg)
        
        has_target_datasets = [dataset for name, dataset in data_bundle.datasets.items() if
                               dataset.has_field('target')]
        target_vocab.index_dataset(*has_target_datasets, field_name='target')
        
        data_bundle.set_vocab(word_vocab, 'words1')
        data_bundle.set_vocab(target_vocab, 'target')

        for name, dataset in data_bundle.datasets.items():
            dataset.add_seq_len('words1', 'seq_len1')
            dataset.add_seq_len('words2', 'seq_len2')

        return data_bundle


class RTEPipe(MatchingPipe):
    """
    处理 **RTE** 数据。

    :param lower: 是否对输入进行小写化。
    :param tokenizer: 使用哪种 tokenize 方式将数据切成单词。支持 ``['spacy', 'raw']`` 。``'raw'`` 表示使用空格作为切分，``'spacy'`` 则使用 :mod:`spacy` 库进行分词。
    :param num_proc: 处理数据时使用的进程数目。
    """
    def process_from_file(self, paths=None):
        r"""
        传入文件路径，生成处理好的 :class:`~fastNLP.io.DataBundle` 对象。``paths`` 支持的路径形式可以参考 :meth:`fastNLP.io.Loader.load`

        :param paths:
        :return:
        """
        data_bundle = RTELoader().load(paths)
        return self.process(data_bundle)


class SNLIPipe(MatchingPipe):
    """
    处理 **SNLI** 数据。

    :param lower: 是否对输入进行小写化。
    :param tokenizer: 使用哪种 tokenize 方式将数据切成单词。支持 ``['spacy', 'raw']`` 。``'raw'`` 表示使用空格作为切分，``'spacy'`` 则使用 :mod:`spacy` 库进行分词。
    :param num_proc: 处理数据时使用的进程数目。
    """
    def process_from_file(self, paths=None):
        r"""
        传入文件路径，生成处理好的 :class:`~fastNLP.io.DataBundle` 对象。``paths`` 支持的路径形式可以参考 :meth:`fastNLP.io.Loader.load`

        :param paths:
        :return:
        """
        data_bundle = SNLILoader().load(paths)
        return self.process(data_bundle)


class QuoraPipe(MatchingPipe):
    """
    处理 **Quora** 数据。

    :param lower: 是否对输入进行小写化。
    :param tokenizer: 使用哪种 tokenize 方式将数据切成单词。支持 ``['spacy', 'raw']`` 。``'raw'`` 表示使用空格作为切分，``'spacy'`` 则使用 :mod:`spacy` 库进行分词。
    :param num_proc: 处理数据时使用的进程数目。
    """
    def process_from_file(self, paths):
        r"""
        传入文件路径，生成处理好的 :class:`~fastNLP.io.DataBundle` 对象。``paths`` 支持的路径形式可以参考 :meth:`fastNLP.io.Loader.load`

        :param paths:
        :return:
        """
        data_bundle = QuoraLoader().load(paths)
        return self.process(data_bundle)


class QNLIPipe(MatchingPipe):
    """
    处理 **QNLI** 数据。

    :param lower: 是否对输入进行小写化。
    :param tokenizer: 使用哪种 tokenize 方式将数据切成单词。支持 ``['spacy', 'raw']`` 。``'raw'`` 表示使用空格作为切分，``'spacy'`` 则使用 :mod:`spacy` 库进行分词。
    :param num_proc: 处理数据时使用的进程数目。
    """
    def process_from_file(self, paths=None):
        r"""
        传入文件路径，生成处理好的 :class:`~fastNLP.io.DataBundle` 对象。``paths`` 支持的路径形式可以参考 :meth:`fastNLP.io.Loader.load`

        :param paths:
        :return:
        """
        data_bundle = QNLILoader().load(paths)
        return self.process(data_bundle)


class MNLIPipe(MatchingPipe):
    """
    处理 **MNLI** 数据。

    :param lower: 是否对输入进行小写化。
    :param tokenizer: 使用哪种 tokenize 方式将数据切成单词。支持 ``['spacy', 'raw']`` 。``'raw'`` 表示使用空格作为切分，``'spacy'`` 则使用 :mod:`spacy` 库进行分词。
    :param num_proc: 处理数据时使用的进程数目。
    """
    def process_from_file(self, paths=None):
        r"""
        传入文件路径，生成处理好的 :class:`~fastNLP.io.DataBundle` 对象。``paths`` 支持的路径形式可以参考 :meth:`fastNLP.io.Loader.load`

        :param paths:
        :return:
        """
        data_bundle = MNLILoader().load(paths)
        return self.process(data_bundle)


class LCQMCPipe(MatchingPipe):
    """
    处理 **LCQMC** 数据。

    :param tokenizer: 使用哪种 tokenize 方式将数据切成单词。支持 ``['cn-char']`` ，按字分词。
    :param num_proc: 处理数据时使用的进程数目。
    """
    def __init__(self, tokenizer='cn-char', num_proc=0):
        super().__init__(tokenizer=tokenizer, num_proc=num_proc)

    def process_from_file(self, paths=None):
        r"""
        传入文件路径，生成处理好的 :class:`~fastNLP.io.DataBundle` 对象。``paths`` 支持的路径形式可以参考 :meth:`fastNLP.io.Loader.load`

        :param paths:
        :return:
        """
        data_bundle = LCQMCLoader().load(paths)
        data_bundle = RenamePipe().process(data_bundle)
        data_bundle = self.process(data_bundle)
        data_bundle = RenamePipe().process(data_bundle)
        return data_bundle


class CNXNLIPipe(MatchingPipe):
    """
    处理 **XNLI Chinese** 数据。

    :param tokenizer: 使用哪种 tokenize 方式将数据切成单词。支持 ``['cn-char']`` ，按字分词。
    :param num_proc: 处理数据时使用的进程数目。
    """
    def __init__(self, tokenizer='cn-char', num_proc=0):
        super().__init__(tokenizer=tokenizer, num_proc=num_proc)

    def process_from_file(self, paths=None):
        r"""
        传入文件路径，生成处理好的 :class:`~fastNLP.io.DataBundle` 对象。``paths`` 支持的路径形式可以参考 :meth:`fastNLP.io.Loader.load`

        :param paths:
        :return:
        """
        data_bundle = CNXNLILoader().load(paths)
        data_bundle = GranularizePipe(task='XNLI').process(data_bundle)
        data_bundle = RenamePipe().process(data_bundle)  # 使中文数据的field
        data_bundle = self.process(data_bundle)
        data_bundle = RenamePipe().process(data_bundle)
        return data_bundle


class BQCorpusPipe(MatchingPipe):
    """
    处理 **BQ Corpus** 数据。
    
    :param tokenizer: 使用哪种 tokenize 方式将数据切成单词。支持 ``['cn-char']`` ，按字分词。
    :param num_proc: 处理数据时使用的进程数目。
    """
    def __init__(self, tokenizer='cn-char', num_proc=0):
        super().__init__(tokenizer=tokenizer, num_proc=num_proc)

    def process_from_file(self, paths=None):
        r"""
        传入文件路径，生成处理好的 :class:`~fastNLP.io.DataBundle` 对象。``paths`` 支持的路径形式可以参考 :meth:`fastNLP.io.Loader.load`

        :param paths:
        :return:
        """
        data_bundle = BQCorpusLoader().load(paths)
        data_bundle = RenamePipe().process(data_bundle)
        data_bundle = self.process(data_bundle)
        data_bundle = RenamePipe().process(data_bundle)
        return data_bundle


class RenamePipe(Pipe):
    """
    重命名数据集的 Pipe ，经过处理后会将数据集中的 ``chars``, ``raw_chars1`` 等列重命名为 ``words``, 
    ``raw_words1``，反之亦然。

    :param task: 任务类型，可选 ``['cn-nli', 'cn-nli-bert']`` 。
    :param num_proc: 处理数据时使用的进程数目。
    """
    def __init__(self, task='cn-nli', num_proc=0):
        super().__init__()
        self.task = task
        self.num_proc = num_proc
    
    def process(self, data_bundle: DataBundle):  # rename field name for Chinese Matching dataset
        """
        :param data_bundle:
        :return: 处理后的 ``data_bundle``
        """
        if (self.task == 'cn-nli'):
            for name, dataset in data_bundle.datasets.items():
                if (dataset.has_field('raw_chars1')):
                    dataset.rename_field('raw_chars1', 'raw_words1')  # RAW_CHARS->RAW_WORDS
                    dataset.rename_field('raw_chars2', 'raw_words2')
                elif (dataset.has_field('words1')):
                    dataset.rename_field('words1', 'chars1')  # WORDS->CHARS
                    dataset.rename_field('words2', 'chars2')
                    dataset.rename_field('raw_words1', 'raw_chars1')
                    dataset.rename_field('raw_words2', 'raw_chars2')
                else:
                    raise RuntimeError(
                        "field name of dataset is not qualified. It should have ether RAW_CHARS or WORDS")
        elif (self.task == 'cn-nli-bert'):
            for name, dataset in data_bundle.datasets.items():
                if (dataset.has_field('raw_chars1')):
                    dataset.rename_field('raw_chars1', 'raw_words1')  # RAW_CHARS->RAW_WORDS
                    dataset.rename_field('raw_chars2', 'raw_words2')
                elif (dataset.has_field('raw_words1')):
                    dataset.rename_field('raw_words1', 'raw_chars1')
                    dataset.rename_field('raw_words2', 'raw_chars2')
                    dataset.rename_field('words', 'chars')
                else:
                    raise RuntimeError(
                        "field name of dataset is not qualified. It should have ether RAW_CHARS or RAW_WORDS"
                    )
        else:
            raise RuntimeError(
                "Only support task='cn-nli' or 'cn-nli-bert'"
            )
        
        return data_bundle


class GranularizePipe(Pipe):
    """
    将数据集中 ``target`` 列中的 tag 按照一定的映射进行重命名，并丢弃不在映射中的 tag。

    :param task: 任务类型，目前仅支持 ``['XNLI']``。

            - ``'XNLI'`` -- 将  ``neutral``, ``entailment``, ``contradictory``, ``contradiction`` 分别
              映射为 0, 1, 2, 3；

    :param num_proc: 处理数据时使用的进程数目。
    """
    def __init__(self, task=None, num_proc=0):
        super().__init__()
        self.task = task
        self.num_proc = num_proc
    
    def _granularize(self, data_bundle, tag_map):
        r"""
        该函数对data_bundle中'target'列中的内容进行转换。

        :param data_bundle:
        :param dict tag_map: 将target列中的tag做以下的映射，比如{"0":0, "1":0, "3":1, "4":1}, 则会删除target为"2"的instance，
            且将"1"认为是第0类。
        :return: 传入的data_bundle
        """
        for name in list(data_bundle.datasets.keys()):
            dataset = data_bundle.get_dataset(name)
            dataset.apply_field(lambda target: tag_map.get(target, -100), field_name='target', new_field_name='target')
            dataset.drop(lambda ins: ins['target'] == -100)
            data_bundle.set_dataset(dataset, name)
        return data_bundle
    
    def process(self, data_bundle: DataBundle):
        """
        :param data_bundle:
        :return: 处理后的 ``data_bundle``
        """
        task_tag_dict = {
            'XNLI': {'neutral': 0, 'entailment': 1, 'contradictory': 2, 'contradiction': 2}
        }
        if self.task in task_tag_dict:
            data_bundle = self._granularize(data_bundle=data_bundle, tag_map=task_tag_dict[self.task])
        else:
            raise RuntimeError(f"Only support {task_tag_dict.keys()} task_tag_map.")
        return data_bundle

class LCQMCBertPipe(MatchingBertPipe):
    """
    处理 **LCQMC** 数据

    :param tokenizer: 使用哪种 tokenize 方式将数据切成单词。支持 ``['cn-char']`` ，按字分词。
    :param num_proc: 处理数据时使用的进程数目。
    """
    def __init__(self, tokenizer='cn-char', num_proc=0):
        super().__init__(tokenizer=tokenizer, num_proc=num_proc)

    def process_from_file(self, paths=None):
        r"""
        传入文件路径，生成处理好的 :class:`~fastNLP.io.DataBundle` 对象。``paths`` 支持的路径形式可以参考 :meth:`fastNLP.io.Loader.load`

        :param paths:
        :return:
        """
        data_bundle = LCQMCLoader().load(paths)
        data_bundle = RenamePipe(task='cn-nli-bert').process(data_bundle)
        data_bundle = self.process(data_bundle)
        data_bundle = TruncateBertPipe(task='cn').process(data_bundle)
        data_bundle = RenamePipe(task='cn-nli-bert').process(data_bundle)
        return data_bundle


class BQCorpusBertPipe(MatchingBertPipe):
    """
    处理 **BQ Corpus** 数据。

    :param tokenizer: 使用哪种 tokenize 方式将数据切成单词。支持 ``['cn-char']`` ，按字分词。
    :param num_proc: 处理数据时使用的进程数目。
    """
    def __init__(self, tokenizer='cn-char', num_proc=0):
        super().__init__(tokenizer=tokenizer, num_proc=num_proc)

    def process_from_file(self, paths=None):
        r"""
        传入文件路径，生成处理好的 :class:`~fastNLP.io.DataBundle` 对象。``paths`` 支持的路径形式可以参考 :meth:`fastNLP.io.Loader.load`

        :param paths:
        :return:
        """
        data_bundle = BQCorpusLoader().load(paths)
        data_bundle = RenamePipe(task='cn-nli-bert').process(data_bundle)
        data_bundle = self.process(data_bundle)
        data_bundle = TruncateBertPipe(task='cn').process(data_bundle)
        data_bundle = RenamePipe(task='cn-nli-bert').process(data_bundle)
        return data_bundle


class CNXNLIBertPipe(MatchingBertPipe):
    """
    处理 **XNLI Chinese** 数据。

    :param tokenizer: 使用哪种 tokenize 方式将数据切成单词。支持 ``['cn-char']`` ，按字分词。
    :param num_proc: 处理数据时使用的进程数目。
    """
    def __init__(self, tokenizer='cn-char', num_proc=0):
        super().__init__(tokenizer=tokenizer, num_proc=num_proc)

    def process_from_file(self, paths=None):
        r"""
        传入文件路径，生成处理好的 :class:`~fastNLP.io.DataBundle` 对象。``paths`` 支持的路径形式可以参考 :meth:`fastNLP.io.Loader.load`

        :param paths:
        :return:
        """
        data_bundle = CNXNLILoader().load(paths)
        data_bundle = GranularizePipe(task='XNLI').process(data_bundle)
        data_bundle = RenamePipe(task='cn-nli-bert').process(data_bundle)
        data_bundle = self.process(data_bundle)
        data_bundle = TruncateBertPipe(task='cn').process(data_bundle)
        data_bundle = RenamePipe(task='cn-nli-bert').process(data_bundle)
        return data_bundle


class TruncateBertPipe(Pipe):
    """
    对数据进行截断的 **Pipe** 。该 **Pipe** 将会寻找每条数据中的第一个分隔符 ``[SEP]`` ，对其前后的数据分别进行截断。
    对于中文任务会将前后的文本分别截断至长度 **250** ，对于英文任务会分别截断至 **215** 。

    :param task: 任务类型，可选 ``['cn', 'en']`` ，分别表示 **中文任务** 和 **英文任务** 。
    :param num_proc: 处理数据时使用的进程数目。
    """
    def __init__(self, task='cn', num_proc=0):
        super().__init__()
        self.task = task
        self.num_proc = num_proc

    def _truncate(self, sentence_index:list, sep_index_vocab):
        # 根据[SEP]在vocab中的index，找到[SEP]在dataset的field['words']中的index
        sep_index_words = sentence_index.index(sep_index_vocab)
        words_before_sep = sentence_index[:sep_index_words]
        words_after_sep = sentence_index[sep_index_words:]  # 注意此部分包括了[SEP]
        if self.task == 'cn':
            # 中文任务将Instance['words']中在[SEP]前后的文本分别截至长度不超过250
            words_before_sep = words_before_sep[:250]
            words_after_sep = words_after_sep[:250]
        elif self.task == 'en':
            # 英文任务将Instance['words']中在[SEP]前后的文本分别截至长度不超过215
            words_before_sep = words_before_sep[:215]
            words_after_sep = words_after_sep[:215]
        else:
            raise RuntimeError("Only support 'cn' or 'en' task.")

        return words_before_sep + words_after_sep

    def process(self, data_bundle: DataBundle) -> DataBundle:
        """
        :param data_bundle:
        :return: 处理后的 ``data_bundle``
        """
        for name in data_bundle.datasets.keys():
            dataset = data_bundle.get_dataset(name)
            sep_index_vocab = data_bundle.get_vocab('words').to_index('[SEP]')
            dataset.apply_field(partial(self._truncate, sep_index_vocab=sep_index_vocab), field_name='words',
                                new_field_name='words', num_proc=self.num_proc)

            # truncate之后需要更新seq_len
            dataset.add_seq_len(field_name='words')
        return data_bundle

