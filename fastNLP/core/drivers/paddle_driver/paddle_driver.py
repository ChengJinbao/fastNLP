import os
import random
from typing import Union, Optional, Dict, Any
from pathlib import Path
from functools import partial
from dataclasses import dataclass

import numpy as np

from .utils import _build_fp16_env, optimizer_state_to_device, DummyGradScaler
from fastNLP.envs.imports import _NEED_IMPORT_PADDLE
from fastNLP.core.drivers.driver import Driver
from fastNLP.core.utils import apply_to_collection, paddle_move_data_to_device
from fastNLP.core.utils.paddle_utils import _convert_data_device
from fastNLP.envs import (
    FASTNLP_MODEL_FILENAME,
    FASTNLP_CHECKPOINT_FILENAME,
    FASTNLP_GLOBAL_RANK,
    rank_zero_call,
)
from fastNLP.core.log import logger
from fastNLP.core.dataloaders import OverfitDataLoader
from fastNLP.core.samplers import (
    ReproducibleBatchSampler,
    ReproducibleSampler,
    ReproduceBatchSampler,
    RandomSampler,
)

if _NEED_IMPORT_PADDLE:
    import paddle
    from paddle.io import (
        DataLoader,
        Dataset,
        Sampler,
        BatchSampler,
        RandomSampler as PaddleRandomSampler,
    )
    from paddle.optimizer import Optimizer

    _reduces = {
        "max": paddle.max,
        "min": paddle.min,
        "mean": paddle.mean,
        "sum": paddle.sum
    }

class PaddleDriver(Driver):
    r"""
    实现了 **PaddlePaddle** 框架训练功能的基本 Driver。

    这个类被以下子类继承：

    1. :class:`~fastNLP.core.drivers.paddle_driver.PaddleSingleDriver`：实现了使用单卡和 ``cpu`` 训练的具体功能；
    2. :class:`~fastNLP.core.drivers.paddle_driver.PaddleFleetDriver`：实现了使用 ``fleet`` 分布式训练 API 进行集群式分布式训练的具体功能；

    .. warning::

        您不应当直接初始化该类，然后传入给 ``Trainer``，换句话说，您应当使用该类的子类 ``PaddleSingleDriver`` 和 ``PaddleDDPDriver``，而不是
        该类本身。

    .. note::

        您可以在使用 ``PaddleSingleDriver`` 和 ``PaddleFleetDriver`` 时使用 ``PaddleDriver`` 提供的接口。

    :param model: 训练时使用的 **PaddlePaddle** 模型
    :param fp16: 是否开启混合精度训练
    :param paddle_kwargs:
    """
    def __init__(self, model: "paddle.nn.Layer", fp16: Optional[bool] = False, paddle_kwargs: Dict = None, **kwargs):
        if not isinstance(model, paddle.nn.Layer):
            raise ValueError(f"Parameter `model` can not be `{type(model)}` in `PaddleDriver`, it should be exactly "
                            f"`paddle.nn.Layer` type.")

        super(PaddleDriver, self).__init__(model)
        self.fp16 = fp16
        self._paddle_kwargs = paddle_kwargs if paddle_kwargs is not None else {}

        # scaler的参数
        self.auto_cast, _grad_scaler = _build_fp16_env(dummy=not fp16)
        self.grad_scaler = _grad_scaler(**self._paddle_kwargs.get("gradscaler_kwargs", {}))

        # 用来设置是否关闭 auto_param_call 中的参数匹配问题；
        self.wo_auto_param_call = kwargs.get("model_wo_auto_param_call", False)

    def zero_grad(self):
        """
        实现梯度置零的过程
        """
        for optimizer in self.optimizers:
            optimizer.clear_grad()

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
        检测 DataLoader 是否合法。支持的类型包括 :class:`~fastNLP.core.dataloaders.PaddleDataLoader`、 :class:`paddle.io.DataLoader` 。

        :param dataloder:
        """
        if not isinstance(dataloader, DataLoader) and not isinstance(dataloader, OverfitDataLoader):
            raise TypeError(f"{DataLoader} is expected, instead of `{type(dataloader)}`")
        if dataloader.batch_size is None and dataloader.batch_sampler is None:
            raise ValueError("Please ensure at least one of your dataloader's batch_size and batch_sampler"
                            "is not None")
        if len(dataloader) == 0:
            logger.rank_zero_warning("Your dataloader is empty, which is not recommended because it "
                                        "may cause some unexpected exceptions.", once=True)

    @staticmethod
    def _check_optimizer_legality(optimizers):
        r"""
        对于用户传入 trainer 的每一个 optimizer检测其合法性，必须为`paddle.optimizer.Optimizer`类型。

        :param optimizers: 需要检测的 `optimizers`。
        """
        for each_optimizer in optimizers:
            if not isinstance(each_optimizer, Optimizer):
                raise TypeError(f"Each optimizer of parameter `optimizers` should be 'paddle.optimizer.Optimizer' type, "
                                 f"not {type(each_optimizer)}.")

    @staticmethod
    def tensor_to_numeric(tensor, reduce=None):
        r"""
        将一个 :class:`paddle.Tensor` 对象转换为 转换成 python 中的数值类型。

        :param tensor: :class:`paddle.Tensor` 类型的对象。
        :param reduce: 当 tensor 是一个多数值的张量时，应当使用何种归一化操作来转换成单一数值，应当为以下类型之一：``['max', 'min', 'sum', 'mean']``。
        :return: 一个单一数值，其数值类型是 python 中的基本的数值类型，例如 ``int，float`` 等。
        """
        if tensor is None:
            return None

        def _translate(_data):
            # 如果只含有一个元素，则返回元素本身，而非list
            if _data.numel().item() == 1:
                return _data.item()
            if reduce is None:
                return _data.tolist()
            else:
                return _reduces[reduce](_data).item()

        return apply_to_collection(
            data=tensor,
            dtype=paddle.Tensor,
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
    def save_model(self, filepath: str, only_state_dict: bool = True, **kwargs):
        r"""
        将模型保存到 ``filepath`` 中。

        :param filepath: 保存文件的文件位置（需要包括文件名）。
        :param only_state_dict: 是否只保存模型的 ``state_dict``；如果为 ``False``，则会调用 ``paddle.jit.save`` 
            函数保存整个模型的参数，此时需要传入 ``input_spec`` 参数。
        :kwargs:
            * *input_spec* -- 描述存储模型 ``forward`` 方法的输入；
              当 ``only_state_dict`` 为 ``False`` 时必须传入，否则加载时会报错。您可以通过 ``InputSpec`` 或者示例 ``Tensor``
              进行描述。详细的使用方法可以参考 **PaddlePaddle** `关于 paddle.jit.save 函数的文档 <https://www.paddlepaddle.org.cn/documentation/docs/zh/api/paddle/jit/save_cn.html#save>`_。
        """
        model = self.unwrap_model()
        if isinstance(filepath, Path):
            filepath = str(filepath)
        if only_state_dict:
            states = {name: param.cpu().detach().clone() for name, param in model.state_dict().items()}
            paddle.save(states, filepath)
        else:
            # paddle 在保存整个模型时需要传入额外参数
            input_spec = kwargs.get("input_spec", None)
            if input_spec is None:
                raise ValueError("To save the whole Paddle Layer, parameter `input_spec` is needed.")
            paddle.jit.save(model, filepath, input_spec)

    def load_model(self, filepath: Union[Path, str], only_state_dict: bool = True, **kwargs):
        """
        加载模型的函数；将 ``filepath`` 中的模型加载并赋值给当前 ``model`` 。

        :param filepath: 保存文件的文件位置
        :param load_state_dict: 保存的内容是否只是权重。
        """
        model = self.unwrap_model()
        if isinstance(filepath, Path):
            filepath = str(filepath)
        # paddle 中，通过 paddle.jit.save 函数保存的模型也可以通过 paddle.load 加载为相应的 state dict
        # 但是此时对输入的 path 有要求，必须是 dir/filename 的形式，否则会报错。
        dirname, filename = os.path.split(filepath)
        if not only_state_dict and dirname == "":
            # 如果传入的是单个文件，则加上相对路径
            filepath = os.path.join(".", filepath)
        model.load_dict(paddle.load(filepath))

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

        # 1. sampler 的状态，因为我们支持 resume training，即精确恢复到具体的一个 batch；
        # paddle 的 DataLoader 在初始化之后 batch_sampler 可能为 None，也可能为用户设置的 batch_sampler
        dataloader_args = self.get_dataloader_args(dataloader)
        if isinstance(dataloader_args.batch_sampler, ReproducibleBatchSampler):
            sampler = dataloader_args.batch_sampler
        elif dataloader_args.sampler:
            sampler = dataloader_args.sampler
        else:
            raise RuntimeError("This condition is not supposed to appear. Please report a bug to us.")

        num_consumed_batches = states.pop("num_consumed_batches")
        if hasattr(sampler, "state_dict") and callable(sampler.state_dict):
            sampler_states = sampler.state_dict()
            if dataloader_args.batch_size is not None:
                sampler_states['num_consumed_samples'] = sampler.num_replicas * dataloader_args.batch_size \
                                                            * num_consumed_batches
            else:
                logger.rank_zero_warning("fastNLP cannot get batch_size, we have to save based on `num_consumed_samples`, "
                                "it may cause missing some samples when reload.")
        else:
            raise RuntimeError(
                "The sampler has no `state_dict()` method, it will fail to recover to the specific batch.")
        
        states['sampler_states'] = sampler_states

        # 2. 保存模型的状态；
        if should_save_model:
            self.save_model(folder.joinpath(FASTNLP_MODEL_FILENAME), only_state_dict, **kwargs)

        # 3. 保存 optimizers 的状态；
        states["optimizers_state_dict"] = self.get_optimizer_state()
        logger.debug("Save optimizer state dict.")

        # 4.保存fp16的状态
        if not isinstance(self.grad_scaler, DummyGradScaler):
            grad_scaler_state_dict = self.grad_scaler.state_dict()
            states['grad_scaler_state_dict'] = grad_scaler_state_dict

        paddle.save(states, str(folder.joinpath(FASTNLP_CHECKPOINT_FILENAME)))

    def get_optimizer_state(self):
        optimizers_state_dict = {}
        for i in range(len(self.optimizers)):
            optimizer: Optimizer = self.optimizers[i]
            optimizers_state_dict[f"optimizer{i}"] = optimizer_state_to_device(optimizer.state_dict(), "cpu")
        
        return optimizers_state_dict

    def load_optimizer_state(self, states):
        assert len(states) == len(self.optimizers), f"The number of optimizers is:{len(self.optimizers)}, while in " \
                                                    f"checkpoint it is:{len(states)}"
        for i in range(len(self.optimizers)):
            optimizer: Optimizer = self.optimizers[i]
            optimizer.set_state_dict(states[f"optimizer{i}"])
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
        states = paddle.load(str(folder.joinpath(FASTNLP_CHECKPOINT_FILENAME)))

        # 1. 加载 optimizers 的状态；
        optimizers_state_dict = states.pop("optimizers_state_dict")
        self.load_optimizer_state(optimizers_state_dict)

        # 2. 加载模型状态；
        if should_load_model:
            self.load_model(folder.joinpath(FASTNLP_MODEL_FILENAME), only_state_dict)

        # 3. 加载fp16的状态；
        if "grad_scaler_state_dict" in states:
            grad_scaler_state_dict = states.pop("grad_scaler_state_dict")
            if not isinstance(self.grad_scaler, DummyGradScaler):
                self.grad_scaler.load_state_dict(grad_scaler_state_dict)
                logger.debug("Load grad_scaler state dict...")
        elif not isinstance(self.grad_scaler, DummyGradScaler):
            logger.rank_zero_warning(f"Checkpoint {folder} is not trained with fp16=True, while resume to a fp16=True training, "
                           f"the training process may be unstable.")

        # 4. 恢复 sampler 的状态；
        dataloader_args = self.get_dataloader_args(dataloader)
        if isinstance(dataloader_args.batch_sampler, ReproducibleBatchSampler):
            sampler = dataloader_args.batch_sampler
        elif isinstance(dataloader_args.sampler, ReproducibleSampler):
            sampler = dataloader_args.sampler
        elif isinstance(dataloader_args.sampler, PaddleRandomSampler):
            sampler = RandomSampler(dataloader_args.sampler.data_source)
            logger.debug("Replace paddle RandomSampler into fastNLP RandomSampler.")
        elif self.is_distributed():
            raise RuntimeError("It is not allowed to use checkpoint retraining when you do not use our or "
                               "`ReproducibleSampler`.")
        else:
            sampler = ReproduceBatchSampler(
                batch_sampler=dataloader_args.batch_sampler if dataloader_args.batch_sampler is not None else dataloader_args.sampler,
                batch_size=dataloader_args.batch_size,
                drop_last=dataloader_args.drop_last
            )
        sampler.load_state_dict(states.pop("sampler_states"))
        states["dataloader"] = self.set_dist_repro_dataloader(dataloader, sampler)

        # 5. 修改 trainer_state.batch_idx_in_epoch
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

    def get_evaluate_context(self):
        r"""
        返回一个不计算梯度的环境用来对模型进行评测。

        :return: 上下文对象 ``paddle.no_grad``;
        """
        return paddle.no_grad

    @staticmethod
    def move_model_to_device(model: "paddle.nn.Layer", device: Union[str, int, "paddle.CUDAPlace", "paddle.CPUPlace"]):
        r"""
        用来将模型 ``model`` 转移到指定的设备上。

        .. note::

            在 **Paddle** 中使用可能会引起因与设置的设备不一致而产生的问题，请注意。

        :param model: 需要进行转移的模型。
        :param device: 目标设备。
        """
        if device is not None:
            model.to(device)

    def move_data_to_device(self, batch: Any) -> Any:
        r"""
        将数据集合 ``batch`` 迁移到指定的机器上。
        
        .. note::

            在 **Paddle** 中使用可能会引起因与设置的设备不一致而产生的问题，请注意。

        :param batch: 包含 :class:`paddle.Tensor` 的数据集合，可以是 **List**、**Dict** 等嵌套类型。
        :return: 移动到指定机器后的 ``batch``。
        """
        device = _convert_data_device(self.data_device)
        return paddle_move_data_to_device(batch, device)

    @staticmethod
    def worker_init_function(worker_id: int, rank: Optional[int] = None) -> None:  # pragma: no cover
        # implementation notes: https://github.com/pytorch/pytorch/issues/5059#issuecomment-817392562
        global_rank = rank if rank is not None else int(os.environ.get(FASTNLP_GLOBAL_RANK, 0))
        # TODO gpu
        process_seed = paddle.fluid.core.default_cpu_generator().initial_seed()
        # back out the base seed so we can use all the bits
        base_seed = process_seed - worker_id
        ss = np.random.SeedSequence([base_seed, worker_id, global_rank])
        # use 128 bits (4 x 32-bit words)
        np.random.seed(ss.generate_state(4))
        # Spawn distinct SeedSequences for the PyTorch PRNG and the stdlib random module
        paddle_ss, stdlib_ss = ss.spawn(2)
        paddle.seed(paddle_ss.generate_state(1, dtype=np.uint64)[0])
        # use 128 bits expressed as an integer
        stdlib_seed = (stdlib_ss.generate_state(2, dtype=np.uint64).astype(object) * [1 << 64, 1]).sum()
        random.seed(stdlib_seed)

    def set_deterministic_dataloader(self, dataloader):
        """
        为了确定性训练要对 ``dataloader`` 进行修改，保证在确定随机数种子后，每次重新训练得到的结果是一样的。 
        """
        if dataloader.worker_init_fn is None:
            dataloader.worker_init_fn = partial(self.worker_init_function, rank=self.global_rank)

    def set_sampler_epoch(self, dataloader: "DataLoader", cur_epoch_idx):
        r"""
        对于分布式的 ``sampler``，需要在每一个 ``epoch`` 前设置随机数种子，来保证每一个进程上的 ``shuffle`` 是一样的。

        :param dataloader: 需要设置 ``epoch`` 的 ``dataloader``
        :param cur_epoch_idx: 当前是第几个 ``epoch``
        """
        if callable(getattr(dataloader.batch_sampler, "set_epoch", None)):
            dataloader.batch_sampler.set_epoch(cur_epoch_idx)
        elif callable(getattr(dataloader.batch_sampler.sampler, "set_epoch", None)):
            dataloader.batch_sampler.sampler.set_epoch(cur_epoch_idx)

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

        # paddle 的 DataLoader 一定会有 dataset 属性；
        res.dataset = dataloader.dataset

        if dataloader.batch_sampler is not None:
            # 不过在 paddle 中，我们限定了 batch_sampler 不能为 None
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
                elif isinstance(dataloader.batch_sampler.sampler, PaddleRandomSampler):
                    res.shuffle = True
                else:
                    res.shuffle = False
            # ReproduceBatchSampler 的情况
            elif hasattr(dataloader.batch_sampler, "batch_sampler"):
                batch_sampler = dataloader.batch_sampler.batch_sampler
                res.sampler = batch_sampler.sampler
                if hasattr(batch_sampler.sampler, "shuffle"):
                    res.shuffle = dataloader.batch_sampler.sampler.shuffle
                elif isinstance(batch_sampler.sampler, PaddleRandomSampler):
                    res.shuffle = True
                else:
                    res.shuffle = False
            else:
                res.sampler = None
                res.shuffle = False

            if hasattr(dataloader.batch_sampler, "drop_last"):
                res.drop_last = getattr(dataloader.batch_sampler, "drop_last")
            # 用户使用的是自己的 batch_sampler 并且其没有 "drop_last" 属性；
            else:
                res.drop_last = False

        return res
