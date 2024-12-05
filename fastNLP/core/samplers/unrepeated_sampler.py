__all__ = [
    'UnrepeatedSampler',
    'UnrepeatedSortedSampler',
    'UnrepeatedRandomSampler',
    "UnrepeatedSequentialSampler"
]

from typing import List, Union
from fastNLP.core.dataset import DataSet

import numpy as np


class UnrepeatedSampler:
    """
    在多卡场景下保证 indice 不重复的 Sampler。
    """
    pass


class UnrepeatedRandomSampler(UnrepeatedSampler):
    """
    考虑在多卡 evaluate 的场景下，不能重复采样。

    :param dataset: 实现了 __len__ 方法的数据容器
    :param shuffle: 如果为 ``True``，将不进行 shuffle，实际上数据会以从长到短的方式输出
    :param seed: 设置的随机数种子
    :param kwargs: fastNLP 内部使用的参数
    """
    def __init__(self, dataset, shuffle: bool = False, seed: int = 0, **kwargs):
        self.dataset = dataset
        self.shuffle = shuffle
        self.seed = int(seed)

        # 多卡的相关的参数
        self.num_replicas = kwargs.get('num_replicas', 1)
        self.rank = kwargs.get('rank', 0)
        self.epoch = kwargs.get('epoch', -1)

    def __len__(self):
        """
        返回 ``Sampler`` 一次完整的迭代过程会产生多少个 index 。多卡的情况下，只考虑 **当前rank** 。
        :return:
        """
        num_common = self.num_samples//self.num_replicas
        num_samples = num_common + int(self.rank < (self.num_samples-num_common*self.num_replicas))
        return num_samples

    def __iter__(self):
        indices = self.generate_indices()

        # subsample
        indices = indices[self.rank:len(indices):self.num_replicas]
        assert len(indices) == len(self)

        for index in indices:
            yield index

    def generate_indices(self) -> List[int]:
        """
        生成随机序列

        :return:
        """
        if self.shuffle:
            indices = list(range(self.num_samples))
            seed = self.seed + self.epoch
            rng = np.random.default_rng(abs(seed))
            rng.shuffle(indices)
            if self.epoch < 0:  # 防止用户忘记调用 set_epoch，至少这样可以保证每次epoch出来的index顺序不同。
                self.epoch -= 1
        else:
            indices = list(range(self.num_samples))
        return indices

    def set_epoch(self, epoch: int) -> None:
        self.epoch = epoch

    def set_distributed(self, num_replicas, rank):
        """
        该方法本质上等同于 ddp 情形下的没有完成的初始化，应当在初始化该 Sampler 本身后立即被调用。

        :param num_replicas: 分布式训练中的进程总数
        :param rank: 当前进程的 ``global_rank``
        :return: 自身
        """
        assert num_replicas<=self.num_samples, f"The number of replicas({num_replicas}) should be lesser than the " \
                                                f"number of samples({self.num_samples})."
        assert num_replicas>0 and isinstance(num_replicas, int)
        assert isinstance(rank, int) and 0<=rank<num_replicas
        # 注意初始化该函数时，所有的状态都应当默认是一个 epoch 刚开始训练的状态；
        self.num_replicas = num_replicas
        self.rank = rank

        return self

    @property
    def num_samples(self):
        """
        样本的总数
        """
        return getattr(self.dataset, 'total_len', len(self.dataset))


class UnrepeatedSortedSampler(UnrepeatedRandomSampler):
    """
    将 ``dataset`` 中的数据根据 ``length`` 从长到短进行迭代，并且保证在多卡场景下数据不重复。
    
    .. note::
    
        本 Sampler 可能导致各个机器上的batch 数量不完全一致。

    :param dataset: 实现了 __len__ 方法的数据容器
    :param length: 每条数据的长度

        * 为 ``List[int]`` 时
         应当与 dataset 有一样的长度，表示 dataset 中每个元素的数量；
        * 为 ``str`` 时
          仅当传入的 ``dataset`` 是 :class:`~fastNLP.DataSet` 时，允许传入 `str` ，该 `str` 将被认为是 ``dataset`` 中的
          ``field`` 。若 field 中的元素为 ``int``，则认为该值是 sample 的长度；若不为 ``int`` ，则尝试使用 ``len`` 方法
          获取该 ``field`` 中每个元素的长度；

    :param kwargs: fastNLP 内部使用的参数
    """
    def __init__(self, dataset, length:Union[str, List], **kwargs):
        kwargs['shuffle'] = False
        kwargs['seed'] = 0
        super().__init__(dataset=dataset, **kwargs)
        if isinstance(dataset, DataSet) and isinstance(length, str):
            length = dataset.get_field(length).content
            if not isinstance(length[0], int):
                length = list(map(len, length))
        else:
            assert len(length) == len(dataset), "When the dataset is not fastNLP.DataSet, " \
                                                "the length parameter can only be List[int]"

        assert len(length) == len(dataset), "The length of `data` and `length` should be equal."

        length = np.array(length, dtype=int)  # 按照长到短排列的序号。
        self.sorted_indices = np.argsort(length)[::-1].tolist()  # 按长度从高到低排序的

    def generate_indices(self) -> List[int]:
        return self.sorted_indices


class UnrepeatedSequentialSampler(UnrepeatedRandomSampler):
    """
    按照顺序读取 dataset。

    :param dataset: 实现了 __len__ 方法的数据容器。
    :param chunk_dist: 如果为 ``True`` ，当多卡时将不间隔索取数据；为 ``False`` 时则会间隔取数据。假设 dataset 有 10 个 sample ，使用
        2 卡，如果为 ``True`` ，卡 **0** 拿 [0, 1, 2, 3, 4], 卡 **1** 拿 [5, 6, 7, 8, 9] ； 如果为 ``False`` ，则卡 **0** 拿 [0, 2, 4, 8, 8], 
        卡 **1** 拿 [1, 3, 5, 7, 9] 。
    :param kwargs:
    """
    def __init__(self, dataset, chunk_dist=False, **kwargs):
        kwargs['shuffle'] = False
        kwargs['seed'] = 0
        super(UnrepeatedSequentialSampler, self).__init__(dataset, **kwargs)
        self.chunk_dist = chunk_dist

    def __iter__(self):
        indices = self.generate_indices()
        if self.num_replicas>1:
            if self.chunk_dist:
                chunk_size = len(indices)//self.num_replicas
                start = chunk_size * self.rank
                end = chunk_size * (self.rank + 1)
                if self.rank == self.num_replicas - 1:
                    end = len(indices)
                indices = indices[start:end]
            else:
                indices = indices[self.rank:len(indices):self.num_replicas]
        for index in indices:
            yield index

    def generate_indices(self) -> List[int]:
        return list(range(self.num_samples))

