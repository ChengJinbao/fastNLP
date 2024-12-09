__all__ = [
    "CSVLoader",
]

from typing import List

from .loader import Loader
from ..file_reader import _read_csv
from fastNLP.core.dataset import DataSet, Instance


class CSVLoader(Loader):
    r"""
    读取CSV格式的数据集, 返回 :class:`~fastNLP.core.DataSet` 。

    :param headers: CSV文件的文件头，定义每一列的属性名称，即返回的 :class:`~fastNLP.core.DataSet` 中 ``field`` 的名称。
        若为 ``None`` ，则将读入文件的第一行视作 ``headers`` 。
    :param sep: CSV文件中列与列之间的分隔符。
    :param dropna: 是否忽略非法数据，若为 ``True`` 则忽略；若为 ``False`` 则在遇到非法数据时抛出 :class:`ValueError`。
    """

    def __init__(self, headers: List[str]=None, sep: str=",", dropna: bool=False):
        super().__init__()
        self.headers = headers
        self.sep = sep
        self.dropna = dropna

    def _load(self, path):
        ds = DataSet()
        for idx, data in _read_csv(path, headers=self.headers,
                                   sep=self.sep, dropna=self.dropna):
            ds.append(Instance(**data))
        return ds

