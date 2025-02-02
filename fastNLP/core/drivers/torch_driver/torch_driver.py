import os
from typing import Union, Dict, Optional, Callable
from functools import partial
import numpy as np
import random
from dataclasses import dataclass
from fastNLP.envs.imports import _NEED_IMPORT_TORCH
from pathlib import Path
if _NEED_IMPORT_TORCH:
    import torch
    from torch.utils.data import DataLoader, IterableDataset, Sampler, BatchSampler, Dataset
    from torch.optim import Optimizer
    from torch.utils.data import RandomSampler as TorchRandomSampler
    _reduces = {
        'sum': torch.sum,
        'min': torch.min,
        'max': torch.max,
        'mean': torch.mean
    }


__all__ = [
    'TorchDriver'
]

from .utils import optimizer_state_to_device
from fastNLP.core.drivers.driver import Driver
from fastNLP.core.drivers.torch_driver.utils import _build_fp16_env, DummyGradScaler
from fastNLP.core.utils import apply_to_collection, torch_move_data_to_device
from fastNLP.envs import rank_zero_call
from fastNLP.envs import FASTNLP_GLOBAL_RANK, FASTNLP_MODEL_FILENAME, FASTNLP_CHECKPOINT_FILENAME
from fastNLP.core.log import logger
from fastNLP.core.samplers import ReproducibleBatchSampler, ReproducibleSampler, ReproduceBatchSampler, RandomSampler
from fastNLP.core.dataloaders import OverfitDataLoader


class TorchDriver(Driver):
    r"""
    专属于 ``pytorch`` 的 ``driver``，是 ``TorchSingleDriver`` 和 ``TorchDDPDriver`` 的父类。

    .. warning::

        您不应当直接初始化该类，然后传入给 ``Trainer``，换句话说，您应当使用该类的子类 ``TorchSingleDriver`` 和 ``TorchDDPDriver``，而不是
        该类本身。

    .. note::

        您可以在使用 ``TorchSingleDriver`` 和 ``TorchDDPDriver`` 时使用 ``TorchDriver`` 提供的接口。

    :param model: 训练时使用的 **pytorch** 模型。
    :param fp16: 是否开启混合精度训练;
    :param torch_kwargs:
    """
    def __init__(self, model, fp16: Optional[bool] = False, torch_kwargs: Dict = None, **kwargs):
        super(TorchDriver, self).__init__(model)

        """ 进行 fp16 的设置 """
        self._torch_kwargs = torch_kwargs if torch_kwargs is not None else {}

        # 因为 ddp 和 single_device 的混合精度训练的设置是一样的，因此可以统一抽象到这里；
        self.fp16 = fp16
        self.auto_cast, _grad_scaler = _build_fp16_env(dummy=not self.fp16)
        self.grad_scaler = _grad_scaler(**self._torch_kwargs.get('gradscaler_kwargs', {}))
        self.set_grad_to_none = self._torch_kwargs.get('set_grad_to_none')

        # 用来设置 `torch_move_data_to_device` 中的 `non_blocking` 参数；
        self.non_blocking = self._torch_kwargs.get("non_blocking", True)

        # 用来设置是否关闭 auto_param_call 中的参数匹配问题；
        self.wo_auto_param_call = kwargs.get("model_wo_auto_param_call", False)

    def zero_grad(self):
        """
        实现梯度置零的过程
        """
        for optimizer in self.optimizers:
            self._clear_grad(optimizer, self.set_grad_to_none)

    def _clear_grad(self, optimizer, set_to_none):
        param_groups = optimizer.param_groups
        for group in param_groups:
            for p in group['params']:
                if p.grad is not None:
                    if set_to_none:
                        p.grad = None
                    else:
                        if p.grad.grad_fn is not None:
                            p.grad.detach_()
                        else:
                            p.grad.requires_grad_(False)
                        p.grad.zero_()

    def backward(self, loss):
        """
        对 ``loss`` 进行反向传播
        """
        self.grad_scaler.scale(loss).backward()

    def step(self):
        r"""
        实现参数的优化更新过程
        """
        for optimizer in self.optimizers:
            self.grad_scaler.step(optimizer)
            self.grad_scaler.update()

    def check_dataloader_legality(self, dataloader):
        """
        检测 DataLoader 是否合法。支持的类型包括 :class:`~fastNLP.core.dataloaders.TorchDataLoader`、 :class:`torch.utils.data.DataLoader` 。

        :param dataloder:
        """
        if not isinstance(dataloader, DataLoader) and not isinstance(dataloader, OverfitDataLoader):
            raise TypeError(f"{DataLoader} is expected, instead of `{type(dataloader)}`")
        if len(dataloader) == 0:
            logger.rank_zero_warning("Your dataloader is empty, which is not recommended because it "
                                        "may cause some unexpected exceptions.", once=True)

    @staticmethod
    def _check_optimizer_legality(optimizers):
        for each_optimizer in optimizers:
            if not isinstance(each_optimizer, Optimizer):
                raise TypeError(f"Each optimizer of parameter `optimizers` should be 'Optimizer' type, "
                                 f"not {type(each_optimizer)}.")

    @staticmethod
    def tensor_to_numeric(tensor, reduce: str = None):
        r"""
        将 ``torch.Tensor`` 转换成 python 中的数值类型。

        :param tensor: ``torch.Tensor``。
        :param reduce: 当 tensor 是一个多数值的张量时，应当使用何种归一化操作来转换成单一数值，应当为以下类型之一：``['max', 'min', 'sum', 'mean']``。
        :return: 一个单一数值，其数值类型是 python 中的基本的数值类型，例如 ``int，float`` 等。
        """

        if tensor is None:
            return None

        def _translate(_data):
            if _data.numel() == 1:
                return _data.item()
            if reduce is None:
                return _data.tolist()
            return _reduces[reduce](_data).item()

        return apply_to_collection(
            data=tensor,
            dtype=torch.Tensor,
            function=_translate
        )

    def set_model_mode(self, mode: str):
        r"""
        设置模型为 ``train`` 或 ``eval`` 的模式；目的是为切换模型的训练和推理（会关闭 dropout 等）模式。

        :param mode: 应为二者之一：``["train", "eval"]``
        """
        assert mode in {"train", "eval"}
        getattr(self.model, mode)()

    @rank_zero_call
    def save_model(self, filepath: Union[str, Path], only_state_dict: bool = True, **kwargs):
        """
        保存当前 driver 的模型到 ``filepath``。

        :param filepath: 保存文件的文件位置
        :param only_state_dict: 是否只保存权重
        :return:
        """
        model = self.unwrap_model()

        if only_state_dict:
            states = {name: param.cpu().detach().clone() for name, param in model.state_dict().items()}
            torch.save(states, filepath)
        else:
            if self.model_device is not None:
                if not self.is_distributed():
                    self.move_model_to_device(model, torch.device("cpu"))
                torch.save(model, filepath)
                if not self.is_distributed():
                    self.move_model_to_device(model, self.model_device)
            else:
                torch.save(model, filepath)

    def load_model(self, filepath: Union[Path, str], only_state_dict: bool = True, **kwargs):
        """
        加载模型的函数；将 ``filepath`` 中的模型加载并赋值给当前 ``model`` 。

        :param filepath: 保存文件的文件位置
        :param load_state_dict: 保存的内容是否只是权重
        """
        model = self.unwrap_model()
        # todo torch.load 在加载时会使得卡 0 多出一个（甚至多个）model 的显存；因此在多卡断点重训时可能会出现错误；
        res = torch.load(filepath, map_location='cpu')
        if isinstance(res, dict) and only_state_dict is False:
            logger.rank_zero_warning(f"It seems like that {filepath} only contains state, you may need to use "
                                     f"`only_state_dict=True`")
        elif not isinstance(res, dict) and only_state_dict is True:
            logger.rank_zero_warning(f"It seems like that {filepath} is not state, you may need to use "
                                     f"`only_state_dict=False`")
        if not isinstance(res, dict):
            res = res.state_dict()
        _strict = kwargs.get("strict", True)
        model.load_state_dict(res, _strict)

    @rank_zero_call
    def save_checkpoint(self, folder: Path, states: Dict, dataloader, only_state_dict: bool = True, should_save_model: bool = True, **kwargs):
        r"""
        断点重训的保存函数，该函数会负责保存 **优化器** 、 **sampler** 和 **fp16** 的状态，以及 **模型** （若 ``should_save_model`` 为 ``True``）

        :param folder: 保存断点重训的状态的文件夹；:meth:`save_checkpoint` 函数应该在该路径下面下面新增名为 ``FASTNLP_CHECKPOINT_FILENAME`` 与
            ``FASTNLP_MODEL_FILENAME`` （如果 ``should_save_model`` 为 ``True`` ）的文件。把 model 相关的内容放入到 ``FASTNLP_MODEL_FILENAME`` 文件
            中，将传入的 ``states`` 以及自身产生的其它状态一并保存在 ``FASTNLP_CHECKPOINT_FILENAME`` 里面。
        :param states: 由 :class:`~fastNLP.core.controllers.Trainer` 传入的一个字典，其中已经包含了为了实现断点重训所需要保存的其它对象的状态。
        :param dataloader: 正在使用的 dataloader。
        :param only_state_dict: 是否只保存模型的参数，当 ``should_save_model`` 为 ``False`` ，该参数无效。
        :param should_save_model: 是否应该保存模型，如果为 ``False`` ，Driver 将不负责 model 的保存。
        """
        # 传入的 dataloader 参数是 trainer 的 dataloader 属性，因为 driver 的所有 dataloader 我们是不会去改变它的，而是通过改变
        #  trainer.dataloader 来改变 dataloader 的状态，从而适配训练或者评测环境；

        # 1. sampler 的状态；
        num_consumed_batches = states.pop('num_consumed_batches')
        states['sampler_states'] = self.get_sampler_state(dataloader, num_consumed_batches)

        # 2. 保存模型的状态；
        if should_save_model:
            if not os.path.exists(folder):
                os.mkdir(folder)
            model_path = folder.joinpath(FASTNLP_MODEL_FILENAME)
            self.save_model(model_path, only_state_dict=only_state_dict)

        # 3. 保存 optimizers 的状态；
        states["optimizers_state_dict"] = self.get_optimizer_state()
        logger.debug("Save optimizer state dict.")

        # 4. 保存fp16的状态
        if not isinstance(self.grad_scaler, DummyGradScaler):
            grad_scaler_state_dict = self.grad_scaler.state_dict()
            states['grad_scaler_state_dict'] = grad_scaler_state_dict

        torch.save(states, Path(folder).joinpath(FASTNLP_CHECKPOINT_FILENAME))

    def get_sampler_state(self, dataloader, num_consumed_batches):
        # 因为我们支持 resume training，即精确恢复到具体的一个 batch；
        # 首先 pytorch 的 DataLoader 一定会有 sampler；另一方面，我们在断点重训的时候一定会在 `set_` 中将 dataloader 的
        #  sampler 替换为 `ReproducibleSampler`；否则就是在单卡情况下将 batch_sampler 替换为 `ReproducibleBatchSampler`；
        dataloader_args = self.get_dataloader_args(dataloader)
        if isinstance(dataloader_args.batch_sampler, ReproducibleBatchSampler):
            sampler = dataloader_args.batch_sampler
        elif dataloader_args.sampler:
            sampler = dataloader_args.sampler
        else:
            raise RuntimeError("This condition is not supposed to appear. Please report a bug to us.")

        if hasattr(sampler, 'state_dict') and callable(sampler.state_dict):
            sampler_states = sampler.state_dict()
            if dataloader_args.batch_size is not None:
                sampler_states['num_consumed_samples'] = sampler.num_replicas * dataloader_args.batch_size \
                                                         * num_consumed_batches
            else:
                logger.rank_zero_warning("fastNLP cannot get batch_size, we have to save based on sampler's "
                                         "`num_consumed_samples`, it may cause missing some samples when reload.")
        else:
            raise RuntimeError('The sampler has no `state_dict()` method, fastNLP cannot save the training '
                               'state.')

        return sampler_states

    def load_sampler_state(self, dataloader, sampler_states):
        states = {}
        dataloader_args = self.get_dataloader_args(dataloader)
        if isinstance(dataloader_args.batch_sampler, ReproducibleBatchSampler):
            sampler = dataloader_args.batch_sampler
        elif isinstance(dataloader_args.sampler, ReproducibleSampler):
            sampler = dataloader_args.sampler
        elif isinstance(dataloader_args.sampler, TorchRandomSampler):
            sampler = RandomSampler(dataloader_args.sampler.data_source)
            logger.debug("Replace torch RandomSampler into fastNLP RandomSampler.")
        elif self.is_distributed():
            raise RuntimeError("It is not allowed to use checkpoint retraining when you do not use our"
                               "`ReproducibleSampler`.")
        else:
            sampler = ReproduceBatchSampler(
                batch_sampler=dataloader_args.batch_sampler if dataloader_args.batch_sampler is not None else dataloader_args.sampler,
                batch_size=dataloader_args.batch_size,
                drop_last=dataloader_args.drop_last
            )
        sampler.load_state_dict(sampler_states)
        states["dataloader"] = self.set_dist_repro_dataloader(dataloader, sampler)

        # 修改 trainer_state.batch_idx_in_epoch
        # sampler 是类似 RandomSampler 的sampler，不是 batch_sampler；
        if not isinstance(sampler, ReproducibleBatchSampler):
            if dataloader_args.drop_last:
                batch_idx_in_epoch = len(
                    sampler) // dataloader_args.batch_size - sampler.num_left_samples // dataloader_args.batch_size
            else:
                batch_idx_in_epoch = (len(sampler) + dataloader_args.batch_size - 1) // dataloader_args.batch_size - \
                    (sampler.num_left_samples + dataloader_args.batch_size - 1) // dataloader_args.batch_size
        # sampler 是 batch_sampler；
        else:
            batch_idx_in_epoch = sampler.batch_idx_in_epoch

        states["batch_idx_in_epoch"] = batch_idx_in_epoch
        return states

    def get_optimizer_state(self):
        optimizers_state_dict = {}
        for i in range(len(self.optimizers)):
            optimizer: torch.optim.Optimizer = self.optimizers[i]
            optimizer_state = optimizer.state_dict()
            optimizer_state["state"] = optimizer_state_to_device(optimizer_state["state"], torch.device("cpu"))
            optimizers_state_dict[f"optimizer{i}"] = optimizer_state  # 注意这里没有使用 deepcopy，测试是不需要的；
        return optimizers_state_dict

    def load_optimizer_state(self, states):
        assert len(states) == len(self.optimizers), f"The number of optimizers is:{len(self.optimizers)}, while in " \
                                                    f"checkpoint it is:{len(states)}"
        for i in range(len(self.optimizers)):
            optimizer: torch.optim.Optimizer = self.optimizers[i]
            optimizer.load_state_dict(states[f"optimizer{i}"])
        logger.debug("Load optimizer state dict.")

    def load_checkpoint(self, folder: Path, dataloader, only_state_dict: bool = True, should_load_model: bool = True, **kwargs) -> Dict:
        r"""
        断点重训的加载函数，该函数会负责读取数据，并且恢复 **优化器** 、**sampler** 、 **fp16** 的状态和 **模型** （如果 ``should_load_model`` 为 True）以及其它
        在 :meth:`save_checkpoint` 函数中执行的保存操作，然后将一个 state 字典返回给 :class:`~fastNLP.core.controllers.Trainer` （ 内容为 :meth:`save_checkpoint` 
        接受到的 ``states`` ）。

        该函数应该在所有 rank 上执行。

        :param folder: 读取该 folder 下的 ``FASTNLP_CHECKPOINT_FILENAME`` 文件与 ``FASTNLP_MODEL_FILENAME``
            （如果 should_load_model 为True）。
        :param dataloader: 当前给定 dataloader，需要根据保存的 dataloader 状态合理设置。若该值为 ``None`` ，则不需要返回 ``'dataloader'``
            以及 ``'batch_idx_in_epoch'`` 这两个值。
        :param only_state_dict: 是否仅读取模型的 state_dict ，当 ``should_save_model`` 为 ``False`` ，该参数无效。如果为 ``True`` ，说明保存的内容为权重；如果为
            False 说明保存的是模型，但也是通过当前 Driver 的模型去加载保存的模型的权重，而不是使用保存的模型替换当前模型。
        :param should_load_model: 是否应该加载模型，如果为 ``False`` ，Driver 将不负责加载模型。若该参数为 ``True`` ，但在保存的状态中没有
            找到对应的模型状态，则报错。
        :return: :meth:`save_checkpoint` 函数输入的 ``states`` 内容。除此之外，还返回的内容有：

            * *dataloader* -- 根据传入的 ``dataloader`` 与读取出的状态设置为合理状态的 dataloader。在当前 ``dataloader`` 样本数与读取出的 sampler 样本数
              不一致时报错。
            * *batch_idx_in_epoch* -- :class:`int` 类型的数据，表明当前 epoch 进行到了第几个 batch 。请注意，该值不能仅通过保存的数据中读取的，因为前后两次运行的
              ``batch_size`` 可能有变化，而应该符合以下等式::

                返回的 dataloader 还会产生的 batch 数量 + batch_idx_in_epoch = 原来不断点训练时的 batch 的总数
              
              由于 ``返回的 dataloader 还会产生的batch数`` 在 ``batch_size`` 与 ``drop_last`` 参数给定的情况下，无法改变，因此只能通过调整 ``batch_idx_in_epoch``
              这个值来使等式成立。一个简单的计算原则如下：

                * drop_last 为 ``True`` 时，等同于 floor(sample_in_this_rank/batch_size) - floor(num_left_samples/batch_size)；
                * drop_last 为 ``False`` 时，等同于 ceil(sample_in_this_rank/batch_size) - ceil(num_left_samples/batch_size)。
        """
        states = torch.load(folder.joinpath(FASTNLP_CHECKPOINT_FILENAME))

        # 1. 加载 optimizers 的状态；
        optimizers_state_dict = states.pop("optimizers_state_dict")
        self.load_optimizer_state(optimizers_state_dict)

        # 2. 加载模型状态；
        if should_load_model:
            self.load_model(filepath=folder.joinpath(FASTNLP_MODEL_FILENAME), only_state_dict=only_state_dict)

        # 3. 加载 fp16 的状态
        if "grad_scaler_state_dict" in states:
            grad_scaler_state_dict = states.pop("grad_scaler_state_dict")
            if not isinstance(self.grad_scaler, DummyGradScaler):
                self.grad_scaler.load_state_dict(grad_scaler_state_dict)
                logger.debug("Load grad_scaler state dict...")
        elif not isinstance(self.grad_scaler, DummyGradScaler):
            logger.rank_zero_warning(f"Checkpoint {folder} is not trained with fp16=True, while resume to a fp16=True training, "
                           f"the training process may be unstable.")

        # 4. 恢复 sampler 的状态；
        sampler_states = states.pop('sampler_states')
        states_ret = self.load_sampler_state(dataloader, sampler_states)
        states.update(states_ret)

        return states

    def get_evaluate_context(self):
        r"""
        返回一个不计算梯度的上下文环境用来对模型进行评测。

        :return: 上下文环境 ``torch.no_grad`` 
        """
        return torch.no_grad

    @staticmethod
    def move_model_to_device(model: "torch.nn.Module", device: "torch.device"):
        r"""
        将模型迁移到对应的设备上
        """
        if device is not None:
            model.to(device)

    def move_data_to_device(self, batch):
        """
        将一个 ``batch`` 的数据迁移到对应的设备上

        :param batch: 包含 :class:`torch.Tensor` 的数据集合，可以是 **List**、**Dict** 等嵌套类型
        :return: 移动到指定机器后的 ``batch``
        """
        return torch_move_data_to_device(batch, self.data_device, self.non_blocking)

    @staticmethod
    def worker_init_function(worker_id: int, rank: Optional[int] = None) -> None:  # pragma: no cover
        """
        """
        """The worker_init_fn that Lightning automatically adds to your dataloader if you previously set the seed
        with ``seed_everything(seed, workers=True)``.

        See also the PyTorch documentation on
        `randomness in DataLoaders <https://pytorch.org/docs/stable/notes/randomness.html#dataloader>`_.
        """
        # implementation notes: https://github.com/pytorch/pytorch/issues/5059#issuecomment-817392562
        global_rank = rank if rank is not None else int(os.environ.get(FASTNLP_GLOBAL_RANK, 0))
        process_seed = torch.initial_seed()
        # back out the base seed so we can use all the bits
        base_seed = process_seed - worker_id
        ss = np.random.SeedSequence([base_seed, worker_id, global_rank])
        # use 128 bits (4 x 32-bit words)
        np.random.seed(ss.generate_state(4))
        # Spawn distinct SeedSequences for the PyTorch PRNG and the stdlib random module
        torch_ss, stdlib_ss = ss.spawn(2)
        torch.manual_seed(torch_ss.generate_state(1, dtype=np.uint64)[0])
        # use 128 bits expressed as an integer
        stdlib_seed = (stdlib_ss.generate_state(2, dtype=np.uint64).astype(object) * [1 << 64, 1]).sum()
        random.seed(stdlib_seed)

    def set_deterministic_dataloader(self, dataloader: "DataLoader"):
        """
        为了确定性训练要对 ``dataloader`` 进行修改，保证在确定随机数种子后，每次重新训练得到的结果是一样的。 
        """
        if dataloader.worker_init_fn is None:
            dataloader.worker_init_fn = partial(self.worker_init_function,
                                                rank=int(os.environ.get(FASTNLP_GLOBAL_RANK, 0)))

    def set_sampler_epoch(self, dataloader: "DataLoader", cur_epoch_idx: int):
        r"""
        对于分布式的 ``sampler``，需要在每一个 ``epoch`` 前设置随机数种子，来保证每一个进程上的 ``shuffle`` 是一样的。

        :param dataloader: 需要设置 ``epoch`` 的 ``dataloader``
        :param cur_epoch_idx: 当前是第几个 ``epoch``
        """
        # 保证 ddp 训练时的 shuffle=True 时的正确性，因为需要保证每一个进程上的 sampler 的shuffle 的随机数种子是一样的；
        if callable(getattr(dataloader.sampler, "set_epoch", None)):
            dataloader.sampler.set_epoch(cur_epoch_idx)

    @staticmethod
    def get_dataloader_args(dataloader: "DataLoader"):
        """
        从 ``dataloader`` 中获取参数 ``dataset``, ``batch_sampler``, ``sampler``, ``batch_size``, ``shuffle`` 
        和 ``drop_last`` 。
        """
        @dataclass
        class Res:
            dataset: Optional[Dataset] = None
            batch_sampler: Optional[BatchSampler] = None
            sampler: Optional[Sampler] = None
            batch_size: Optional[int] = None
            shuffle: Optional[bool] = None
            drop_last: Optional[bool] = None

        res = Res()

        # pytorch 的 DataLoader 一定会有 dataset 属性；
        res.dataset = dataloader.dataset

        # dataloader 使用的是 sampler；
        if dataloader.batch_sampler is None:
            res.sampler = dataloader.sampler
            res.batch_size = 1
            res.shuffle = True if isinstance(dataloader.sampler, RandomSampler) else False
            res.drop_last = False
        # dataloader 使用的是 batch_sampler；
        else:
            res.batch_sampler = dataloader.batch_sampler
            if hasattr(dataloader.batch_sampler, "batch_size"):
                res.batch_size = getattr(dataloader.batch_sampler, "batch_size")
            # 用户使用的是自己的 batch_sampler 并且其没有 "batch_size" 属性；
            else:
                dataloader_iter = iter(dataloader)
                pre_sample = next(dataloader_iter)
                res.batch_size = pre_sample.shape[0]

            if hasattr(dataloader.batch_sampler, "sampler"):
                res.sampler = dataloader.batch_sampler.sampler
                if hasattr(dataloader.batch_sampler.sampler, "shuffle"):
                    res.shuffle = dataloader.batch_sampler.sampler.shuffle
                elif isinstance(dataloader.batch_sampler.sampler, TorchRandomSampler):
                    res.shuffle = True
                else:
                    res.shuffle = False
            # ReproduceBatchSampler 的情况
            elif hasattr(dataloader.batch_sampler, "batch_sampler"):
                batch_sampler = dataloader.batch_sampler.batch_sampler
                res.sampler = batch_sampler.sampler
                if hasattr(batch_sampler.sampler, "shuffle"):
                    res.shuffle = dataloader.batch_sampler.sampler.shuffle
                elif isinstance(batch_sampler.sampler, TorchRandomSampler):
                    res.shuffle = True
                else:
                    res.shuffle = False
            else:
                # 如果 dataloader.batch_sampler 没有 sampler 这个属性，那么说明其使用的是自己的 batch_sampler，且没有 "sampler" 属性；
                #  这种情况下 DataLoader 会自己初始化一个 sampler；我们因此将这个默认初始化的 sampler 挂载到 res 上；
                res.sampler = dataloader.sampler
                res.shuffle = False

            if hasattr(dataloader.batch_sampler, "drop_last"):
                res.drop_last = getattr(dataloader.batch_sampler, "drop_last")
            # 用户使用的是自己的 batch_sampler 并且其没有 "drop_last" 属性；
            else:
                res.drop_last = False

        return res
