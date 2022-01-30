"""
.. todo::
    doc
"""
__all__ = [
    'DataBundle',
]

from ..core.dataset import DataSet
from ..core.vocabulary import Vocabulary


class DataBundle:
    """
    经过处理的数据信息，包括一系列数据集（比如：分开的训练集、验证集和测试集）以及各个field对应的vocabulary。该对象一般由fastNLP中各种
    Loader的load函数生成，可以通过以下的方法获取里面的内容

    Example::
        
        data_bundle = YelpLoader().load({'train':'/path/to/train', 'dev': '/path/to/dev'})
        train_vocabs = data_bundle.vocabs['train']
        train_data = data_bundle.datasets['train']
        dev_data = data_bundle.datasets['train']

    :param vocabs: 从名称(字符串)到 :class:`~fastNLP.Vocabulary` 类型的dict
    :param datasets: 从名称(字符串)到 :class:`~fastNLP.DataSet` 类型的dict
    """

    def __init__(self, vocabs: dict = None, datasets: dict = None):
        self.vocabs = vocabs or {}
        self.datasets = datasets or {}

    def set_vocab(self, vocab, field_name):
        """
        向DataBunlde中增加vocab

        :param ~fastNLP.Vocabulary vocab: 词表
        :param str field_name: 这个vocab对应的field名称
        :return: self
        """
        assert isinstance(vocab, Vocabulary), "Only fastNLP.Vocabulary supports."
        self.vocabs[field_name] = vocab
        return self

    def set_dataset(self, dataset, name):
        """

        :param ~fastNLP.DataSet dataset: 传递给DataBundle的DataSet
        :param str name: dataset的名称
        :return: self
        """
        self.datasets[name] = dataset
        return self

    def get_dataset(self, name: str) -> DataSet:
        """
        获取名为name的dataset

        :param str name: dataset的名称，一般为'train', 'dev', 'test'
        :return: DataSet
        """
        return self.datasets[name]

    def delete_dataset(self, name: str):
        """
        删除名为name的DataSet

        :param str name:
        :return: self
        """
        self.datasets.pop(name, None)
        return self

    def get_vocab(self, field_name: str) -> Vocabulary:
        """
        获取field名为field_name对应的vocab

        :param str field_name: 名称
        :return: Vocabulary
        """
        return self.vocabs[field_name]

    def delete_vocab(self, field_name: str):
        """
        删除vocab
        :param str field_name:
        :return: self
        """
        self.vocabs.pop(field_name, None)
        return self

    def set_input(self, *field_names, flag=True, use_1st_ins_infer_dim_type=True, ignore_miss_dataset=True):
        """
        将field_names中的field设置为input, 对data_bundle中所有的dataset执行该操作::

            data_bundle.set_input('words', 'seq_len')   # 将words和seq_len这两个field的input属性设置为True
            data_bundle.set_input('words', flag=False)  # 将words这个field的input属性设置为False

        :param str field_names: field的名称
        :param bool flag: 将field_name的input状态设置为flag
        :param bool use_1st_ins_infer_dim_type: 如果为True，将不会check该列是否所有数据都是同样的维度，同样的类型。将直接使用第一
            行的数据进行类型和维度推断本列的数据的类型和维度。
        :param bool ignore_miss_dataset: 当某个field名称在某个dataset不存在时，如果为True，则直接忽略该DataSet;
            如果为False，则报错
        :return: self
        """
        for field_name in field_names:
            for name, dataset in self.datasets.items():
                if not ignore_miss_dataset and not dataset.has_field(field_name):
                    raise KeyError(f"Field:{field_name} was not found in DataSet:{name}")
                if not dataset.has_field(field_name):
                    continue
                else:
                    dataset.set_input(field_name, flag=flag, use_1st_ins_infer_dim_type=use_1st_ins_infer_dim_type)
        return self

    def set_target(self, *field_names, flag=True, use_1st_ins_infer_dim_type=True, ignore_miss_dataset=True):
        """
        将field_names中的field设置为target, 对data_bundle中所有的dataset执行该操作::

            data_bundle.set_target('target', 'seq_len')   # 将words和target这两个field的input属性设置为True
            data_bundle.set_target('target', flag=False)  # 将target这个field的input属性设置为False

        :param str field_names: field的名称
        :param bool flag: 将field_name的target状态设置为flag
        :param bool use_1st_ins_infer_dim_type: 如果为True，将不会check该列是否所有数据都是同样的维度，同样的类型。将直接使用第一
            行的数据进行类型和维度推断本列的数据的类型和维度。
        :param bool ignore_miss_dataset: 当某个field名称在某个dataset不存在时，如果为True，则直接忽略该DataSet;
            如果为False，则报错
        :return: self
        """
        for field_name in field_names:
            for name, dataset in self.datasets.items():
                if not ignore_miss_dataset and not dataset.has_field(field_name):
                    raise KeyError(f"Field:{field_name} was not found in DataSet:{name}")
                if not dataset.has_field(field_name):
                    continue
                else:
                    dataset.set_target(field_name, flag=flag, use_1st_ins_infer_dim_type=use_1st_ins_infer_dim_type)
        return self

    def copy_field(self, field_name, new_field_name, ignore_miss_dataset=True):
        """
        将DataBundle中所有的field_name复制一份叫new_field_name.

        :param str field_name:
        :param str new_field_name:
        :param bool ignore_miss_dataset: 当某个field名称在某个dataset不存在时，如果为True，则直接忽略该DataSet;
            如果为False，则报错
        :return: self
        """
        for name, dataset in self.datasets.items():
            if dataset.has_field(field_name=field_name):
                dataset.copy_field(field_name=field_name, new_field_name=new_field_name)
            elif not ignore_miss_dataset:
                raise KeyError(f"{field_name} not found DataSet:{name}.")
        return self

    def apply_field(self, func, field_name:str, new_field_name:str, ignore_miss_dataset=True,  **kwargs):
        """
        对DataBundle中所有的dataset使用apply方法

        :param callable func: input是instance中名为 `field_name` 的field的内容。
        :param str field_name: 传入func的是哪个field。
        :param str new_field_name: 将func返回的内容放入到 `new_field_name` 这个field中，如果名称与已有的field相同，则覆
            盖之前的field。如果为None则不创建新的field。
        :param bool ignore_miss_dataset: 当某个field名称在某个dataset不存在时，如果为True，则直接忽略该DataSet;
            如果为False，则报错
        :param optional kwargs: 支持输入is_input,is_target,ignore_type

            1. is_input: bool, 如果为True则将名为 `new_field_name` 的field设置为input

            2. is_target: bool, 如果为True则将名为 `new_field_name` 的field设置为target

            3. ignore_type: bool, 如果为True则将名为 `new_field_name` 的field的ignore_type设置为true, 忽略其类型
        """
        for name, dataset in self.datasets.items():
            if dataset.has_field(field_name=field_name):
                dataset.apply_field(func=func, field_name=field_name, new_field_name=new_field_name, **kwargs)
            elif not ignore_miss_dataset:
                raise KeyError(f"{field_name} not found DataSet:{name}.")
        return self

    def apply(self, func, new_field_name:str, **kwargs):
        """
        对DataBundle中所有的dataset使用apply方法

        :param callable func: input是instance中名为 `field_name` 的field的内容。
        :param str new_field_name: 将func返回的内容放入到 `new_field_name` 这个field中，如果名称与已有的field相同，则覆
            盖之前的field。如果为None则不创建新的field。
        :param optional kwargs: 支持输入is_input,is_target,ignore_type

            1. is_input: bool, 如果为True则将名为 `new_field_name` 的field设置为input

            2. is_target: bool, 如果为True则将名为 `new_field_name` 的field设置为target

            3. ignore_type: bool, 如果为True则将名为 `new_field_name` 的field的ignore_type设置为true, 忽略其类型
        """
        for name, dataset in self.datasets.items():
            dataset.apply(func, new_field_name=new_field_name, **kwargs)
        return self

    def __repr__(self):
        _str = 'In total {} datasets:\n'.format(len(self.datasets))
        for name, dataset in self.datasets.items():
            _str += '\t{} has {} instances.\n'.format(name, len(dataset))
        _str += 'In total {} vocabs:\n'.format(len(self.vocabs))
        for name, vocab in self.vocabs.items():
            _str += '\t{} has {} entries.\n'.format(name, len(vocab))
        return _str


