__all__ = [
    "CLSBaseLoader",
    "YelpFullLoader",
    "YelpPolarityLoader",
    "AGsNewsLoader",
    "DBPediaLoader",
    "IMDBLoader",
    "SSTLoader",
    "SST2Loader",
    "ChnSentiCorpLoader",
    "THUCNewsLoader",
    "WeiboSenti100kLoader",

    "MRLoader",
    "R8Loader",
    "R52Loader",
    "OhsumedLoader",
    "NG20Loader",
]

import glob
import os
import random
import shutil
import time

from .loader import Loader
from fastNLP.core.dataset import Instance, DataSet
from fastNLP.core.log import logger

class CLSBaseLoader(Loader):
    r"""
    文本分类 Loader 的一个基类

    原始数据中内容应该为：每一行为一个 sample ，第一个逗号之前为 **target** ，第一个逗号之后为 **文本内容** 。

    Example::

        "1","I got 'new' tires from the..."
        "1","Don't waste your time..."

    读取的 :class:`~fastNLP.core.DataSet` 将具备以下的数据结构：

    .. csv-table::
       :header: "raw_words", "target"

       "I got 'new' tires from them and... ", "1"
       "Don't waste your time.  We had two...", "1"
       "...", "..."

    """

    def __init__(self, sep=',', has_header=False):
        super().__init__()
        self.sep = sep
        self.has_header = has_header

    def _load(self, path: str):
        ds = DataSet()
        try:
            with open(path, 'r', encoding='utf-8') as f:
                read_header = self.has_header
                for line in f:
                    if read_header:
                        read_header = False
                        continue
                    line = line.strip()
                    sep_index = line.index(self.sep)
                    target = line[:sep_index]
                    raw_words = line[sep_index + 1:]
                    if target.startswith("\""):
                        target = target[1:]
                    if target.endswith("\""):
                        target = target[:-1]
                    if raw_words.endswith("\""):
                        raw_words = raw_words[:-1]
                    if raw_words.startswith('"'):
                        raw_words = raw_words[1:]
                    raw_words = raw_words.replace('""', '"')  # 替换双引号
                    if raw_words:
                        ds.append(Instance(raw_words=raw_words, target=target))
        except Exception as e:
            logger.error(f'Fail to load `{path}`.')
            raise e
        return ds


def _split_dev(dataset_name, data_dir, dev_ratio=0.0, re_download=False, suffix='csv'):
    if dev_ratio == 0.0:
        return data_dir
    modify_time = 0
    for filepath in glob.glob(os.path.join(data_dir, '*')):
        modify_time = os.stat(filepath).st_mtime
        break
    if time.time() - modify_time > 1 and re_download:  # 通过这种比较丑陋的方式判断一下文件是否是才下载的
        shutil.rmtree(data_dir)
        data_dir = Loader()._get_dataset_path(dataset_name=dataset_name)

    if not os.path.exists(os.path.join(data_dir, f'dev.{suffix}')):
        if dev_ratio > 0:
            assert 0 < dev_ratio < 1, "dev_ratio should be in range (0,1)."
            try:
                with open(os.path.join(data_dir, f'train.{suffix}'), 'r', encoding='utf-8') as f, \
                        open(os.path.join(data_dir, f'middle_file.{suffix}'), 'w', encoding='utf-8') as f1, \
                        open(os.path.join(data_dir, f'dev.{suffix}'), 'w', encoding='utf-8') as f2:
                    for line in f:
                        if random.random() < dev_ratio:
                            f2.write(line)
                        else:
                            f1.write(line)
                os.remove(os.path.join(data_dir, f'train.{suffix}'))
                os.renames(os.path.join(data_dir, f'middle_file.{suffix}'), os.path.join(data_dir, f'train.{suffix}'))
            finally:
                if os.path.exists(os.path.join(data_dir, f'middle_file.{suffix}')):
                    os.remove(os.path.join(data_dir, f'middle_file.{suffix}'))

    return data_dir


class AGsNewsLoader(CLSBaseLoader):
    """
    **AG's News** 数据集的 **Loader**，如果您使用了这个数据集，请引用以下的文章

        Xiang Zhang, Junbo Zhao, Yann LeCun. Character-level Convolutional Networks for Text Classification. Advances
        in Neural Information Processing Systems 28 (NIPS 2015)
    """
    def download(self):
        r"""
        自动下载数据集。

        :return: 数据集的目录地址
        """
        return self._get_dataset_path(dataset_name='ag-news')


class DBPediaLoader(CLSBaseLoader):
    """
    **DBpedia** 数据集的 **Loader**。如果您使用了这个数据集，请引用以下的文章

        Xiang Zhang, Junbo Zhao, Yann LeCun. Character-level Convolutional Networks for Text Classification. Advances
        in Neural Information Processing Systems 28 (NIPS 2015)
    """
    def download(self, dev_ratio: float = 0.0, re_download: bool = False):
        r"""
        自动下载数据集。下载完成后在 ``output_dir`` 中有 ``train.csv`` , ``test.csv`` , ``dev.csv`` 三个文件。
        如果 ``dev_ratio`` 为 0，则只有 ``train.csv`` 和 ``test.csv`` 。

        :param dev_ratio: 如果路径中没有验证集 ，从 train 划分多少作为 dev 的数据。如果为 **0** ，则不划分 dev
        :param re_download: 是否重新下载数据，以重新切分数据。
        :return: 数据集的目录地址
        """
        dataset_name = 'dbpedia'
        data_dir = self._get_dataset_path(dataset_name=dataset_name)
        data_dir = _split_dev(dataset_name=dataset_name,
                              data_dir=data_dir,
                              dev_ratio=dev_ratio,
                              re_download=re_download,
                              suffix='csv')
        return data_dir


class IMDBLoader(CLSBaseLoader):
    r"""
    **IMDb** 数据集的 **Loader** ，如果您使用了这个数据集，请引用以下的文章

        http://www.aclweb.org/anthology/P11-1015。
        
    原始数据中内容应该为：每一行为一个 sample ，制表符之前为 **target** ，制表符之后为 **文本内容** 。

    Example::

        neg	Alan Rickman & Emma...
        neg	I have seen this...

    **IMDBLoader** 读取后的 :class:`~fastNLP.core.DataSet` 将具有以下两列内容: ``raw_words`` 代表需要分类的文本，``target`` 代表文本的标签：

    .. csv-table::
       :header: "raw_words", "target"

       "Alan Rickman & Emma... ", "neg"
       "I have seen this... ", "neg"
       "...", "..."

    """

    def __init__(self):
        super().__init__(sep='\t')

    def download(self, dev_ratio: float = 0.0, re_download=False):
        r"""
        自动下载数据集。

        根据 ``dev_ratio`` 的值随机将 train 中的数据取出一部分作为 dev 数据。

        :param dev_ratio: 如果路径中没有 ``dev.txt`` ，从 train 划分多少作为 dev 的数据。 如果为 **0** ，则不划分 dev
        :param re_download: 是否重新下载数据，以重新切分数据。
        :return: 数据集的目录地址
        """
        dataset_name = 'aclImdb'
        data_dir = self._get_dataset_path(dataset_name=dataset_name)
        data_dir = _split_dev(dataset_name=dataset_name,
                              data_dir=data_dir,
                              dev_ratio=dev_ratio,
                              re_download=re_download,
                              suffix='txt')
        return data_dir


class SSTLoader(Loader):
    r"""
    **SST** 数据集的 **Loader**，如果您使用了这个数据集，请引用以下的文章

            https://nlp.stanford.edu/~socherr/EMNLP2013_RNTN.pdf

    原始数据中内容应该为::

        (2 (3 (3 Effective) (2 but)) (1 (1 too-tepid)...
        (3 (3 (2 If) (3 (2 you) (3 (2 sometimes)...

    读取的 :class:`~fastNLP.core.DataSet` 将具备以下的数据结构：

    .. csv-table:: 下面是使用 SSTLoader 读取的 DataSet 所具备的 field
        :header: "raw_words"

        "(2 (3 (3 Effective) (2 but)) (1 (1 too-tepid)..."
        "(3 (3 (2 If) (3 (2 you) (3 (2 sometimes) ..."
        "..."

    ``raw_words`` 列是 :class:`str` 。

    """

    def __init__(self):
        super().__init__()

    def _load(self, path: str):
        r"""
        从path读取SST文件

        :param str path: 文件路径
        :return: DataSet
        """
        ds = DataSet()
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    ds.append(Instance(raw_words=line))
        return ds

    def download(self):
        r"""
        自动下载数据集。

        :return: 数据集的目录地址
        """
        output_dir = self._get_dataset_path(dataset_name='sst')
        return output_dir


class YelpFullLoader(CLSBaseLoader):
    """
    **Yelp Review Full** 数据集的 **Loader**，如果您使用了这个数据集，请引用以下的文章

        Xiang Zhang, Junbo Zhao, Yann LeCun. Character-level Convolutional Networks for Text Classification. Advances
        in Neural Information Processing Systems 28 (NIPS 2015)
    """
    def download(self, dev_ratio: float = 0.0, re_download: bool = False):
        r"""
        自动下载数据集。下载完成后在 ``output_dir`` 中有 ``train.csv`` , ``test.csv`` , ``dev.csv`` 三个文件。
        如果 ``dev_ratio`` 为 0，则只有 ``train.csv`` 和 ``test.csv`` 。

        :param dev_ratio: 如果路径中没有验证集 ，从 train 划分多少作为 dev 的数据。如果为 **0** ，则不划分 dev
        :param re_download: 是否重新下载数据，以重新切分数据。
        :return: 数据集的目录地址
        """
        dataset_name = 'yelp-review-full'
        data_dir = self._get_dataset_path(dataset_name=dataset_name)
        data_dir = _split_dev(dataset_name=dataset_name,
                              data_dir=data_dir,
                              dev_ratio=dev_ratio,
                              re_download=re_download,
                              suffix='csv')
        return data_dir


class YelpPolarityLoader(CLSBaseLoader):
    """
    **Yelp Review Polarity** 数据集的 **Loader**，如果您使用了这个数据集，请引用以下的文章

        Xiang Zhang, Junbo Zhao, Yann LeCun. Character-level Convolutional Networks for Text Classification. Advances
        in Neural Information Processing Systems 28 (NIPS 2015)
    """
    def download(self, dev_ratio: float = 0.0, re_download: bool = False):
        r"""
        自动下载数据集。下载完成后在 ``output_dir`` 中有 ``train.csv`` , ``test.csv`` , ``dev.csv`` 三个文件。
        如果 ``dev_ratio`` 为 0，则只有 ``train.csv`` 和 ``test.csv`` 。

        :param dev_ratio: 如果路径中没有验证集 ，从 train 划分多少作为 dev 的数据。如果为 **0** ，则不划分 dev
        :param re_download: 是否重新下载数据，以重新切分数据。
        :return: 数据集的目录地址
        """
        dataset_name = 'yelp-review-polarity'
        data_dir = self._get_dataset_path(dataset_name=dataset_name)
        data_dir = _split_dev(dataset_name=dataset_name,
                              data_dir=data_dir,
                              dev_ratio=dev_ratio,
                              re_download=re_download,
                              suffix='csv')
        return data_dir


class SST2Loader(Loader):
    r"""
    **SST-2** 数据集的 **Loader**，如果您使用了该数据集，请引用以下的文章

    https://nlp.stanford.edu/pubs/SocherBauerManningNg_ACL2013.pdf
    
    原始数据中内容应该为：第一行为标题（具体内容会被忽略），之后每一行为一个 sample ，第一个制表符之前是 **句子** ，
    第一个制表符之后认为是 **label** 。

    Example::

        sentence	label
        it 's a charming and often affecting journey . 	1
        unflinchingly bleak and desperate 	0

    读取的 :class:`~fastNLP.core.DataSet` 将具备以下的数据结构：

    .. csv-table::
        :header: "raw_words", "target"

        "it 's a charming and often affecting journey .", "1"
        "unflinchingly bleak and desperate", "0"
        "..."

    测试集的 :class:`~fastNLP.core.DataSet` 没有 ``target`` 列。
    """

    def __init__(self):
        super().__init__()

    def _load(self, path: str):
        r"""从path读取SST2文件

        :param str path: 数据路径
        :return: DataSet
        """
        ds = DataSet()

        with open(path, 'r', encoding='utf-8') as f:
            f.readline()  # 跳过header
            if 'test' in os.path.split(path)[1]:
                logger.warning("SST2's test file has no target.")
                for line in f:
                    line = line.strip()
                    if line:
                        sep_index = line.index('\t')
                        raw_words = line[sep_index + 1:]
                        index = int(line[: sep_index])
                        if raw_words:
                            ds.append(Instance(raw_words=raw_words, index=index))
            else:
                for line in f:
                    line = line.strip()
                    if line:
                        raw_words = line[:-2]
                        target = line[-1]
                        if raw_words:
                            ds.append(Instance(raw_words=raw_words, target=target))
        return ds

    def download(self):
        r"""
        自动下载数据集。

        :return:
        """
        output_dir = self._get_dataset_path(dataset_name='sst-2')
        return output_dir


class ChnSentiCorpLoader(Loader):
    r"""
    **ChnSentiCorp** 数据集的 **Loader**，该数据取自 https://github.com/pengming617/bert_classification/tree/master/data，在
    https://arxiv.org/pdf/1904.09223.pdf 与 https://arxiv.org/pdf/1906.08101.pdf 有使用。

    支持读取的数据的格式为：第一行为标题（具体内容会被忽略），之后每一行为一个 sample，第一个制表符之前被认为是 **label** ，第
    一个制表符之后认为是 **句子** 。

    Example::

        label	text_a
        1	基金痛所有投资项目一样，必须先要有所了解...
        1	系统很好装，LED屏是不错，就是16比9的比例...

    读取的 :class:`~fastNLP.core.DataSet` 将具备以下的数据结构：

    .. csv-table::
        :header: "raw_chars", "target"

        "基金痛所有投资项目一样，必须先要有所了解...", "1"
        "系统很好装，LED屏是不错，就是16比9的比例...", "1"
        "..."

    """

    def __init__(self):
        super().__init__()

    def _load(self, path: str):
        r"""
        从path中读取数据

        :param path:
        :return:
        """
        ds = DataSet()
        with open(path, 'r', encoding='utf-8') as f:
            f.readline()
            for line in f:
                line = line.strip()
                tab_index = line.index('\t')
                if tab_index != -1:
                    target = line[:tab_index]
                    raw_chars = line[tab_index + 1:]
                    if raw_chars:
                        ds.append(Instance(raw_chars=raw_chars, target=target))
        return ds

    def download(self) -> str:
        r"""
        自动下载数据。

        :return: 数据集的目录地址
        """
        output_dir = self._get_dataset_path('chn-senti-corp')
        return output_dir


class THUCNewsLoader(Loader):
    r"""
    **THUCNews** 数据集的 **Loader**，该数据取自
    http://thuctc.thunlp.org/#%E4%B8%AD%E6%96%87%E6%96%87%E6%9C%AC%E5%88%86%E7%B1%BB%E6%95%B0%E6%8D%AE%E9%9B%86THUCNews
    
    数据用于 document-level 分类任务，新闻 10 分类。
    原始数据内容为：每行一个 sample，第一个 ``"\t"`` 之前为 **target** ，第一个 ``"\t"`` 之后为 **raw_words** 。

    Example::

        体育	调查-您如何评价热火客场胜绿军总分3-1夺赛点？...

    读取的 :class:`~fastNLP.core.DataSet` 将具备以下的数据结构：

    .. csv-table::
        :header: "raw_words", "target"

        "调查-您如何评价热火客场胜绿军总分3-1夺赛点？...", "体育"
        "...", "..."

    """

    def __init__(self):
        super(THUCNewsLoader, self).__init__()

    def _load(self, path: str = None):
        ds = DataSet()
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                sep_index = line.index('\t')
                raw_chars = line[sep_index + 1:]
                target = line[:sep_index]
                if raw_chars:
                    ds.append(Instance(raw_chars=raw_chars, target=target))
        return ds

    def download(self) -> str:
        r"""
        自动下载数据。

        :return: 数据集目录地址
        """
        output_dir = self._get_dataset_path('thuc-news')
        return output_dir


class WeiboSenti100kLoader(Loader):
    r"""
    **WeiboSenti100k** 数据集的 **Loader**，该数据取自 https://github.com/SophonPlus/ChineseNlpCorpus/，
    在 https://arxiv.org/abs/1906.08101 有使用。微博 sentiment classification，二分类。

    Example::

        label	text
        1	多谢小莲，好运满满[爱你]
        1	能在他乡遇老友真不赖，哈哈，珠儿，我也要用...

    读取的 :class:`~fastNLP.core.DataSet` 将具备以下的数据结构：

    .. csv-table::
        :header: "raw_chars", "target"

        "多谢小莲，好运满满[爱你]", "1"
        "能在他乡遇老友真不赖，哈哈，珠儿，我也要用...", "1"
        "...", "..."

    """

    def __init__(self):
        super(WeiboSenti100kLoader, self).__init__()

    def _load(self, path: str = None):
        ds = DataSet()
        with open(path, 'r', encoding='utf-8') as f:
            next(f)
            for line in f:
                line = line.strip()
                target = line[0]
                raw_chars = line[1:]
                if raw_chars:
                    ds.append(Instance(raw_chars=raw_chars, target=target))
        return ds

    def download(self) -> str:
        r"""
        自动下载数据。

        :return: 数据集目录地址
        """
        output_dir = self._get_dataset_path('weibo-senti-100k')
        return output_dir


class MRLoader(CLSBaseLoader):
    """
    **MR** 数据集的 **Loader**
    """
    def __init__(self):
        super(MRLoader, self).__init__()

    def download(self, dev_ratio: float = 0.0, re_download: bool = False) -> str:
        r"""
        自动下载数据集。下载完成后在 ``output_dir`` 中有 ``train.csv`` , ``test.csv`` , ``dev.csv`` 三个文件。
        如果 ``dev_ratio`` 为 0，则只有 ``train.csv`` 和 ``test.csv`` 。

        :param dev_ratio: 如果路径中没有验证集 ，从 train 划分多少作为 dev 的数据。如果为 **0** ，则不划分 dev
        :param re_download: 是否重新下载数据，以重新切分数据。
        :return: 数据集的目录地址
        """
        dataset_name = r'mr'
        data_dir = self._get_dataset_path(dataset_name=dataset_name)
        data_dir = _split_dev(dataset_name=dataset_name,
                              data_dir=data_dir,
                              dev_ratio=dev_ratio,
                              re_download=re_download,
                              suffix='csv')
        return data_dir


class R8Loader(CLSBaseLoader):
    """
    **R8** 数据集的 **Loader**
    """
    def __init__(self):
        super(R8Loader, self).__init__()

    def download(self, dev_ratio: float = 0.0, re_download: bool = False) -> str:
        r"""
        自动下载数据集。下载完成后在 ``output_dir`` 中有 ``train.csv`` , ``test.csv`` , ``dev.csv`` 三个文件。
        如果 ``dev_ratio`` 为 0，则只有 ``train.csv`` 和 ``test.csv`` 。

        :param dev_ratio: 如果路径中没有验证集 ，从 train 划分多少作为 dev 的数据。如果为 **0** ，则不划分 dev
        :param re_download: 是否重新下载数据，以重新切分数据。
        :return: 数据集的目录地址
        """
        dataset_name = r'R8'
        data_dir = self._get_dataset_path(dataset_name=dataset_name)
        data_dir = _split_dev(dataset_name=dataset_name,
                              data_dir=data_dir,
                              dev_ratio=dev_ratio,
                              re_download=re_download,
                              suffix='csv')
        return data_dir


class R52Loader(CLSBaseLoader):
    """
    **R52** 数据集的 **Loader**
    """
    def __init__(self):
        super(R52Loader, self).__init__()

    def download(self, dev_ratio: float = 0.0, re_download: bool = False) -> str:
        r"""
        自动下载数据集。下载完成后在 ``output_dir`` 中有 ``train.csv`` , ``test.csv`` , ``dev.csv`` 三个文件。
        如果 ``dev_ratio`` 为 0，则只有 ``train.csv`` 和 ``test.csv`` 。

        :param dev_ratio: 如果路径中没有验证集 ，从 train 划分多少作为 dev 的数据。如果为 **0** ，则不划分 dev
        :param re_download: 是否重新下载数据，以重新切分数据。
        :return: 数据集的目录地址
        """
        dataset_name = r'R52'
        data_dir = self._get_dataset_path(dataset_name=dataset_name)
        data_dir = _split_dev(dataset_name=dataset_name,
                              data_dir=data_dir,
                              dev_ratio=dev_ratio,
                              re_download=re_download,
                              suffix='csv')
        return data_dir


class NG20Loader(CLSBaseLoader):
    """
    **NG20** 数据集的 **Loader**
    """
    def __init__(self):
        super(NG20Loader, self).__init__()

    def download(self, dev_ratio: float = 0.0, re_download: bool = False) -> str:
        r"""
        自动下载数据集。下载完成后在 ``output_dir`` 中有 ``train.csv`` , ``test.csv`` , ``dev.csv`` 三个文件。
        如果 ``dev_ratio`` 为 0，则只有 ``train.csv`` 和 ``test.csv`` 。

        :param dev_ratio: 如果路径中没有验证集 ，从 train 划分多少作为 dev 的数据。如果为 **0** ，则不划分 dev
        :param re_download: 是否重新下载数据，以重新切分数据。
        :return: 数据集的目录地址
        """
        dataset_name = r'20ng'
        data_dir = self._get_dataset_path(dataset_name=dataset_name)
        data_dir = _split_dev(dataset_name=dataset_name,
                              data_dir=data_dir,
                              dev_ratio=dev_ratio,
                              re_download=re_download,
                              suffix='csv')
        return data_dir


class OhsumedLoader(CLSBaseLoader):
    """
    **Ohsumed** 数据集的 **Loader**
    """
    def __init__(self):
        super(OhsumedLoader, self).__init__()

    def download(self, dev_ratio: float = 0.0, re_download: bool = False) -> str:
        r"""
        自动下载数据集。下载完成后在 ``output_dir`` 中有 ``train.csv`` , ``test.csv`` , ``dev.csv`` 三个文件。
        如果 ``dev_ratio`` 为 0，则只有 ``train.csv`` 和 ``test.csv`` 。

        :param dev_ratio: 如果路径中没有验证集 ，从 train 划分多少作为 dev 的数据。如果为 **0** ，则不划分 dev
        :param re_download: 是否重新下载数据，以重新切分数据。
        :return: 数据集的目录地址
        """
        dataset_name = r'ohsumed'
        data_dir = self._get_dataset_path(dataset_name=dataset_name)
        data_dir = _split_dev(dataset_name=dataset_name,
                              data_dir=data_dir,
                              dev_ratio=dev_ratio,
                              re_download=re_download,
                              suffix='csv')
        return data_dir
