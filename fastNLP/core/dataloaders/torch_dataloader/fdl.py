__all__ = [
    'TorchDataLoader',
    'prepare_torch_dataloader'
]

from typing import Optional, Callable, Sequence, Union, Tuple, Dict, Mapping, List
from copy import deepcopy

from fastNLP.core.dataset import DataSet
from fastNLP.core.collators import Collator
from fastNLP.core.dataloaders.utils import indice_collate_wrapper
from fastNLP.envs.imports import _NEED_IMPORT_TORCH
from fastNLP.core.samplers import ReproducibleBatchSampler, ReproducibleSampler, UnrepeatedSampler, RandomSampler
from ..utils import _match_param

if _NEED_IMPORT_TORCH:
    from torch.utils.data import DataLoader, Sampler
else:
    from fastNLP.core.utils.dummy_class import DummyClass as DataLoader


class _FDataSet:
    """
    对Dataset的封装，主要是修改dataset的__getitem__函数，增加返回下标idx，值得注意的是dataset需要实现__getattribute__函数才能在_FDataset
    中调用dataset的方法
    """

    def __init__(self, dataset) -> None:
        self.dataset = dataset

    def __getitem__(self, item: Union[int, list]) -> Tuple:
        return (item, self.dataset[item])

    def __getattr__(self, item):
        try:
            return self.dataset.__getattribute__(item)
        except AttributeError as e:
            raise e

    def __len__(self) -> int:
        return len(self.dataset)


class TorchDataLoader(DataLoader):
    """
    提供给``torch``框架使用的``DataLoader``函数，``TorchDataLoader``提供了``Collator``的功能，用户可以通过设置``collate_fn="auto"``来
    使用，并可以配套使用``set_pad``和``set_ignore``方法设置p``ad_val``和忽略某个field的pad操作。
    """

    def __init__(self, dataset, batch_size: int = 16,
                 shuffle: bool = False, sampler: Union["Sampler[int]", ReproducibleSampler, UnrepeatedSampler] = None,
                 batch_sampler: Union["Sampler[Sequence[int]]", ReproducibleBatchSampler] = None,
                 num_workers: int = 0, collate_fn: Union[Callable, str, None] = 'auto',
                 pin_memory: bool = False, drop_last: bool = False,
                 timeout: float = 0, worker_init_fn: Optional[Callable] = None,
                 multiprocessing_context=None, generator=None, prefetch_factor: int = 2,
                 persistent_workers: bool = False, **kwargs) -> None:
        """

        :param dataset: 实现了__getitem__和__len__的数据容器
        :param batch_size: 批次大小，当batch_sampler为None生效
        :param shuffle: 是否打乱数据集
        :param sampler: 实现了__len__和__iter__方法的实例化对象，其功能是每次返回dataset的一个index，当其不为None时，shuffle参数无效
        :param batch_sampler: 实现了__len__和__iter__方法的实例化对象，，其能迭代返回一个list的index数据, index不超过dataset的大小，
        当其不为None时，bacth_size,sampler,shuffle均无效。
        :param num_workers: 开启子进程的数量，当num_worker=0时不开启多进程
        :param collate_fn:用来对从dataset取到的数据进行打包处理成batch的callable函数，其值应该为一下三个:``[None, "auto", callable]``.

            * ``callate_fn=None``时，第一点值得注意的是此时传进来的datset不能为``fastNLP``的dataset,采用fastNLP的dataset时，``collate_fn``不能为``None``;
            第二点注意的是此时``TorchDataLoader``会调用默认的`default_collate_fn`函数对sampler到的数据进行简单打包，组成一个batch返回。`
            * ``callate_fn="auto"``时，``TorchDataLoader``会自动调用``fastNLP``自带的``Collator``，其会自动检测dataset的每个``field``,
            并判断是否能够pad处理，若能则会自动进行pad操作，默认``pad_val=0``。若想要更改其值，可调用``set_pad``方法;若不想自动pad某个field，
            可以调用``set_ignore``方法忽略某个field。
            * ``callate_fn=callable``时，callable函数是用户自定义的callate_fn函数，此时``TorchDataLoader``会调用传进来的callable函数对
            数据进行打包处理并返回。值得注意的是用户自定义的callable函数的输入为batch,batch为list类型数据，其中batch的每一条数据都为dataset的一条数据。

        :param pin_memory: 如果其为True, 那么DataLoader会在返回数据张量之前将其copy到cuda的pin memory中。
        :param drop_last: 当``drop_last=True``时，``TorchDataLoader``会扔掉最后一个不能组成``batch_size``大小的batch数据;
        若``drop_last=False``, 则什么也不做。
        :param timeout: 从子进程的输出队列获取数据的超时值
        :param worker_init_fn: init函数，如果不设置为None,则将会在每个子进程初始化时调用该函数。
        :param multiprocessing_context: 多进程的上下文环境
        :param generator: 如果其不为None, 将会使用RandomSampler去生成随机的index并且多进程会每个子进程生成一个``base_seed``
        :param prefetch_factor: 每个worker提前装载的samples数量。``2``意味着在所有的进程中会有2*num_workers的数据被预取。默认值为2.
        :param persistent_workers: 如果其为True, dataloader会在迭代完一次dataset后不会所有进程。默认为False

        """
        if isinstance(dataset, DataSet) and collate_fn is None:
            raise ValueError("When use FastNLP DataSet, collate_fn must be not None")

        if not isinstance(dataset, _FDataSet):
            dataset = _FDataSet(dataset)

        if batch_sampler is not None:
            batch_size = 1
            shuffle = False
            sampler = None
        elif sampler is None:
            sampler = RandomSampler(dataset, shuffle=shuffle)
            shuffle = False

        if isinstance(collate_fn, str):
            if collate_fn == 'auto':
                if isinstance(dataset.dataset, DataSet):  # 使用了 fastnlp dataset
                    collate_fn = deepcopy(dataset.dataset.collator)
                    collate_fn.set_backend(backend="torch")
                else:
                    collate_fn = Collator(backend="torch")
            else:
                raise ValueError(f"collate_fn: {collate_fn} must be 'auto'")

        dl_kwargs = _match_param(TorchDataLoader.__init__, DataLoader.__init__, fn_name=DataLoader.__name__)
        if dl_kwargs is None:
            super().__init__(dataset=dataset, batch_size=batch_size, shuffle=shuffle, sampler=sampler,
                             batch_sampler=batch_sampler, num_workers=num_workers, collate_fn=collate_fn,
                             pin_memory=pin_memory, drop_last=drop_last, timeout=timeout, worker_init_fn=worker_init_fn,
                             multiprocessing_context=multiprocessing_context, generator=generator,
                             prefetch_factor=prefetch_factor,
                             persistent_workers=persistent_workers)
        else:
            super().__init__(**dl_kwargs)

        self.cur_batch_indices = None

    def __iter__(self):
        self.collate_fn = indice_collate_wrapper(self.collate_fn)
        for indices, data in super().__iter__():
            self.cur_batch_indices = indices
            yield data

    def set_pad(self, field_name: Union[str, tuple], pad_val: Union[int, float, None] = 0, dtype=None, backend=None,
                pad_fn: Callable = None) -> Collator:
        """
        如果需要对某个 field 的内容进行特殊的调整，请使用这个函数。

        :param field_name: 需要调整的 field 的名称。如果 Dataset 的 __getitem__ 方法返回的是 dict 类型的，则可以直接使用对应的
            field 的 key 来表示，如果是 nested 的 dict，可以使用元组表示多层次的 key，例如 {'a': {'b': 1}} 中的使用 ('a', 'b');
            如果 __getitem__ 返回的是 Sequence 类型的，则可以使用 '_0', '_1' 表示序列中第 0 或 1 个元素。如果该 field 在数据中没
            有找到，则报错；如果 __getitem__ 返回的是就是整体内容，请使用 "_single" 。
        :param pad_val: 这个 field 的默认 pad 值。如果设置为 None，则表示该 field 不需要 pad , fastNLP 默认只会对可以 pad 的
            field 进行 pad，所以如果对应 field 本身就不是可以 pad 的形式，可以不需要主动设置为 None 。如果 backend 为 None ，该值
            无意义。
        :param dtype: 对于需要 pad 的 field ，该 field 的数据 dtype 应该是什么。
        :param backend: 可选['raw', 'numpy', 'torch', 'torch', 'jittor', 'auto']，分别代表，输出为 list, numpy.ndarray,
            torch.Tensor, torch.Tensor, jittor.Var 类型。若 pad_val 为 None ，该值无意义 。
        :param pad_fn: 指定当前 field 的 pad 函数，传入该函数则 pad_val, dtype, backend 等参数失效。pad_fn 的输入为当前 field 的
            batch 形式。 Collator 将自动 unbatch 数据，然后将各个 field 组成各自的 batch 。pad_func 的输入即为 field 的 batch
            形式，输出将被直接作为结果输出。
        :return: 返回 Collator
        """
        collator = self._get_collator()
        if isinstance(collator, Collator):
            collator.set_pad(field_name=field_name, pad_val=pad_val, dtype=dtype, pad_fn=pad_fn, backend=backend)
            return collator
        else:
            raise ValueError(f"Only when the collate_fn is a fastNLP Collator, set_pad() is allowed.")

    def _get_collator(self):
        """
        如果 collate_fn 是 Collator 对象，得到该对象。如果没有的话，返回 None

        :return:
        """
        collator = None
        if hasattr(self.collate_fn, '__wrapped__') and isinstance(self.collate_fn.__wrapped__, Collator):
            collator = self.collate_fn.__wrapped__
        elif isinstance(self.collate_fn, Collator):
            collator = self.collate_fn
        return collator

    def set_ignore(self, *field_names) -> Collator:
        """
        如果有的内容不希望输出，可以在此处进行设置，被设置的 field 将在 batch 的输出中被忽略。
        Example::

            collator.set_ignore('field1', 'field2')

        :param field_names: 需要忽略的 field 的名称。如果 Dataset 的 __getitem__ 方法返回的是 dict 类型的，则可以直接使用对应的
            field 的 key 来表示，如果是 nested 的 dict，可以使用元组来表示，例如 {'a': {'b': 1}} 中的使用 ('a', 'b'); 如果
            __getitem__ 返回的是 Sequence 类型的，则可以使用 '_0', '_1' 表示序列中第 0 或 1 个元素。
        :return: 返回 Collator 自身
        """
        collator = self._get_collator()
        if isinstance(collator, Collator):
            collator.set_ignore(*field_names)
            return collator
        else:
            raise ValueError(f"Only when the collate_fn is a fastNLP Collator, set_ignore() is allowed.")

    def get_batch_indices(self) -> List[int]:
        """
        获取当前 ``batch`` 中每条数据对应的索引。

        :return: 当前 ``batch`` 数据的索引；
        """
        return self.cur_batch_indices


def prepare_torch_dataloader(ds_or_db,
                             train_batch_size: int = 16,
                             shuffle: bool = False,
                             train_sampler: Union["Sampler[int]", ReproducibleSampler, UnrepeatedSampler] = None,
                             batch_sampler: Union["Sampler[Sequence[int]]", ReproducibleBatchSampler] = None,
                             num_workers: int = 0, collate_fn: Union[Callable, str, None] = 'auto',
                             pin_memory: bool = False, drop_last: bool = False,
                             timeout: float = 0, worker_init_fn: Optional[Callable] = None,
                             multiprocessing_context=None, generator=None, prefetch_factor: int = 2,
                             persistent_workers: bool = False, non_train_sampler: Optional["Sampler[int]"] = None,
                             non_train_batch_size: int = 16) \
        -> Union[TorchDataLoader, Dict[str, TorchDataLoader], Sequence[TorchDataLoader]]:
    """
    prepare_torch_dataloader的功能是将多个dataset同时转为dataloader返回。ds_or_db的类型只能为``[Dataset, DataBundle,
     Sequence[Dataset], Dict[name, Dataset]]``,具体如下:

        * 当ds_or_db为Dataset时，prepare_torch_dataloader会将所有的参数除了non_train_batch_size以外来帮你实例化一个
        torchDataLoader并返回。
        * 当ds_or_db为FastNLP的DataBundle时，prepare_torch_dataloader会遍历所有的dataset并根据其name实例化不同的torchDataLoader，
        当name中包含'train'字符串时，prepare_torch_dataloader默认其为train数据，并将train_batch_size传为其中，其他不包含'train'字符串
        的dataset均使用non_train_batch_size作为batch_size来实例化torchDataLoader。最终根据name:torchDataLoader组成一个Dict[name, torchDataLoader]
        的数据返回。
        * 当ds_or_db为Dict[name, Dataset]数据类型时，prepare_torch_dataloader会遍历所有的dataset并根据其name实例化不同的torchDataLoader，
        当name中包含'train'字符串时，prepare_torch_dataloader默认其为train数据，并将train_batch_size传为其中，其他不包含'train'字符串
        的dataset均使用non_train_batch_size作为batch_size来实例化torchDataLoader。最终根据name:torchDataLoader组成一个Dict[name, torchDataLoader]
        的数据返回。
        * 当ds_or_db为Sequence[Dataset]数据类型时， prepare_torch_dataloader会将Sequence[0]作为默认的train数据集对待，并使用train_batch_size作为
        其batch_size使用;而Sequence[1:]均视为非train数据集对待，使用non_train_batch_size作为batch_size来实例化torchDataLoader。最终
        将所有torchDataLoader组成Sequence[torchDataLoader]返回。

    :param ds_or_db: 传进来的dataset集合或字典或为dataset或DataBundle。其取值只能为``[Dataset, DataBundle,
     Sequence[Dataset], Dict[name, Dataset]]``.
    :param shuffle: 是否打乱数据集
    :param train_batch_size: 'train'数据集使用的batch_size，跟non_train_batch_size是互斥的。
    :param non_train_batch_size: 非'train'数据使用batch_size，跟train_batch_size是互斥的。
    :param train_sampler: train'数据集使用的sampler, 现了__len__和__iter__方法的实例化对象，其功能是每次返回dataset的一个index，当其不为None时，shuffle参数无效
    :param non_train_sampler: 非'train'数据使用sampler, 实现了__len__和__iter__方法的实例化对象，其功能是每次返回dataset的一个index，当其不为None时，shuffle参数无效
    :param batch_sampler: 实现了__len__和__iter__方法的实例化对象，，其能迭代返回一个list的index数据, index不超过dataset的大小，
    当其不为None时，bacth_size,sampler,shuffle均无效。
    :param num_workers: 开启子进程的数量，当num_worker=0时不开启多进程
    :param collate_fn:用来对从dataset取到的数据进行打包处理成batch的callable函数，其值应该为一下三个:``[None, "auto", callable]``.

        * ``callate_fn=None``时，第一点值得注意的是此时传进来的datset不能为``fastNLP``的dataset,采用fastNLP的dataset时，``collate_fn``不能为``None``;
        第二点注意的是此时``TorchDataLoader``会调用默认的`default_collate_fn`函数对sampler到的数据进行简单打包，组成一个batch返回。`
        * ``callate_fn="auto"``时，``TorchDataLoader``会自动调用``fastNLP``自带的``Collator``，其会自动检测dataset的每个``field``,
        并判断是否能够pad处理，若能则会自动进行pad操作，默认``pad_val=0``。若想要更改其值，可调用``set_pad``方法;若不想自动pad某个field，
        可以调用``set_ignore``方法忽略某个field。
        * ``callate_fn=callable``时，callable函数是用户自定义的callate_fn函数，此时``TorchDataLoader``会调用传进来的callable函数对
        数据进行打包处理并返回。值得注意的是用户自定义的callable函数的输入为batch,batch为list类型数据，其中batch的每一条数据都为dataset的一条数据。

    :param pin_memory: 如果其为True, 那么DataLoader会在返回数据张量之前将其copy到cuda的pin memory中。
    :param drop_last: 当``drop_last=True``时，``TorchDataLoader``会扔掉最后一个不能组成``batch_size``大小的batch数据;
    若``drop_last=False``, 则什么也不做。
    :param timeout: 从子进程的输出队列获取数据的超时值
    :param worker_init_fn: init函数，如果不设置为None,则将会在每个子进程初始化时调用该函数。
    :param multiprocessing_context: 多进程的上下文环境
    :param generator: 如果其不为None, 将会使用RandomSampler去生成随机的index并且多进程会每个子进程生成一个``base_seed``
    :param prefetch_factor: 每个worker提前装载的samples数量。``2``意味着在所有的进程中会有2*num_workers的数据被预取。默认值为2.
    :param persistent_workers: 如果其为True, dataloader会在迭代完一次dataset后不会所有进程。默认为False
    """

    from fastNLP.io import DataBundle
    if isinstance(ds_or_db, DataSet):
        dl = TorchDataLoader(dataset=ds_or_db, batch_size=train_batch_size,
                             shuffle=shuffle, sampler=train_sampler, batch_sampler=batch_sampler,
                             num_workers=num_workers, collate_fn=collate_fn, pin_memory=pin_memory,
                             drop_last=drop_last, timeout=timeout, worker_init_fn=worker_init_fn,
                             multiprocessing_context=multiprocessing_context, generator=generator,
                             prefetch_factor=prefetch_factor, persistent_workers=persistent_workers,
                             )
        return dl

    elif isinstance(ds_or_db, DataBundle):
        dl_bundle = {}
        for name, ds in ds_or_db.iter_datasets():
            if 'train' in name:
                dl_bundle[name] = TorchDataLoader(dataset=ds, batch_size=train_batch_size,
                                                  shuffle=shuffle, sampler=train_sampler, batch_sampler=batch_sampler,
                                                  num_workers=num_workers, collate_fn=collate_fn, pin_memory=pin_memory,
                                                  drop_last=drop_last, timeout=timeout, worker_init_fn=worker_init_fn,
                                                  multiprocessing_context=multiprocessing_context, generator=generator,
                                                  prefetch_factor=prefetch_factor,
                                                  persistent_workers=persistent_workers,
                                                  )
            else:
                dl_bundle[name] = TorchDataLoader(dataset=ds,
                                                  batch_size=non_train_batch_size if non_train_batch_size else train_batch_size,
                                                  shuffle=shuffle,
                                                  sampler=non_train_sampler if non_train_sampler else train_sampler,
                                                  batch_sampler=batch_sampler,
                                                  num_workers=num_workers, collate_fn=collate_fn, pin_memory=pin_memory,
                                                  drop_last=drop_last, timeout=timeout, worker_init_fn=worker_init_fn,
                                                  multiprocessing_context=multiprocessing_context, generator=generator,
                                                  prefetch_factor=prefetch_factor,
                                                  persistent_workers=persistent_workers,
                                                  )
        return dl_bundle

    elif isinstance(ds_or_db, Sequence):
        dl_bundle = []
        for idx, ds in enumerate(ds_or_db):
            if idx > 0:
                train_batch_size = non_train_batch_size if non_train_batch_size else train_batch_size
                train_sampler = non_train_sampler if non_train_sampler else train_sampler
            dl_bundle.append(
                TorchDataLoader(dataset=ds, batch_size=train_batch_size,
                                shuffle=shuffle, sampler=train_sampler, batch_sampler=batch_sampler,
                                num_workers=num_workers, collate_fn=collate_fn, pin_memory=pin_memory,
                                drop_last=drop_last, timeout=timeout, worker_init_fn=worker_init_fn,
                                multiprocessing_context=multiprocessing_context, generator=generator,
                                prefetch_factor=prefetch_factor, persistent_workers=persistent_workers,
                                )
            )
        return dl_bundle

    elif isinstance(ds_or_db, Mapping):
        dl_bundle = {}
        for name, ds in ds_or_db.items():
            if 'train' in name:
                dl_bundle[name] = TorchDataLoader(dataset=ds, batch_size=train_batch_size,
                                                  shuffle=shuffle, sampler=train_sampler, batch_sampler=batch_sampler,
                                                  num_workers=num_workers, collate_fn=collate_fn, pin_memory=pin_memory,
                                                  drop_last=drop_last, timeout=timeout, worker_init_fn=worker_init_fn,
                                                  multiprocessing_context=multiprocessing_context, generator=generator,
                                                  prefetch_factor=prefetch_factor,
                                                  persistent_workers=persistent_workers,
                                                  )
            else:
                dl_bundle[name] = TorchDataLoader(dataset=ds,
                                                  batch_size=non_train_batch_size if non_train_batch_size else train_batch_size,
                                                  shuffle=shuffle,
                                                  sampler=non_train_sampler if non_train_sampler else train_sampler,
                                                  batch_sampler=batch_sampler,
                                                  num_workers=num_workers, collate_fn=collate_fn, pin_memory=pin_memory,
                                                  drop_last=drop_last, timeout=timeout, worker_init_fn=worker_init_fn,
                                                  multiprocessing_context=multiprocessing_context, generator=generator,
                                                  prefetch_factor=prefetch_factor,
                                                  persistent_workers=persistent_workers,
                                                  )

        return dl_bundle
    else:
        raise ValueError(f"ds_or_db: {ds_or_db} must be fastnlp dataset or data_bundle or sequence or mapping!")
