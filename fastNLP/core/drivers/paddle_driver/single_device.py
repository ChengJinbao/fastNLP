import os
import contextlib
from typing import Optional, Dict, Union, Callable, Tuple

from .paddle_driver import PaddleDriver
from .utils import replace_batch_sampler, replace_sampler
from fastNLP.envs.imports import _NEED_IMPORT_PADDLE
from fastNLP.envs.env import USER_CUDA_VISIBLE_DEVICES
from fastNLP.core.utils import (
    auto_param_call,
    get_paddle_gpu_str,
    get_paddle_device_id,
)
from fastNLP.core.utils.paddle_utils import _convert_data_device
from fastNLP.core.utils.utils import _get_fun_msg
from fastNLP.core.samplers import (
    ReproducibleBatchSampler,
    ReproduceBatchSampler,
    ReproducibleSampler,
    RandomSampler,
    re_instantiate_sampler,
)
from fastNLP.core.log import logger

if _NEED_IMPORT_PADDLE:
    import paddle
    from paddle import DataParallel
    from paddle.fluid.reader import _DatasetKind
    from paddle.io import (
        RandomSampler as PaddleRandomSampler,
        SequenceSampler as PaddleSequenialSampler,
        BatchSampler as PaddleBatchSampler,
    )

__all__ = [
    "PaddleSingleDriver",
]

class PaddleSingleDriver(PaddleDriver):
    """
    实现了 **PaddlePaddle** 框架下在单卡或 ``cpu`` 环境下训练功能的 **Driver**。

    :param model: 训练时使用的 **PaddlePaddle** 模型
    :param device: 训练使用的设备
    :param fp16: 是否开启混合精度训练
    :param paddle_kwargs:
        * *gradscaler_kwargs* -- 用于 ``fp16=True`` 时，提供给 :class:`paddle.amp.GradScaler` 的参数。
    :kwargs:
        * *model_wo_auto_param_call* (``bool``) -- 是否关闭在训练时调用我们的 ``auto_param_call`` 函数来自动匹配 batch 和前向函数的参数的行为。

        .. note::

            关于该参数的详细说明，请参见 :class:`~fastNLP.core.controllers.Trainer` 中的描述；函数 ``auto_param_call`` 详见 :func:`fastNLP.core.utils.auto_param_call`。

    """
    def __init__(self, model: "paddle.nn.Layer", device: Union[str, int], fp16: Optional[bool] = False, paddle_kwargs: Dict = None, **kwargs):
        if isinstance(model, DataParallel):
            raise ValueError("`paddle.DataParallel` is not supported in `PaddleSingleDriver`")

        cuda_visible_devices = os.getenv(USER_CUDA_VISIBLE_DEVICES)
        if cuda_visible_devices == "":
            device = "cpu"
            logger.info("You have set `CUDA_VISIBLE_DEVICES` to '' in system environment variable, and we are gonna to"
                        "use `cpu` instead of `gpu` device.")

        super(PaddleSingleDriver, self).__init__(model, fp16=fp16, paddle_kwargs=paddle_kwargs, **kwargs)

        if device is None:
            raise ValueError("Parameter `device` can not be None in `PaddleSingleDriver`.")

        if device != "cpu":
            device_id = get_paddle_device_id(device)
            if cuda_visible_devices is not None:
                os.environ["CUDA_VISIBLE_DEVICES"] = cuda_visible_devices.split(",")[device_id]
        self.model_device = get_paddle_gpu_str(device)

        self.local_rank = 0
        self.global_rank = 0
        self.world_size = 1

    def setup(self):
        r"""
        初始化训练环境；设置当前训练的设备，并将模型迁移到对应设备上。
        """
        device = _convert_data_device(self.data_device)

        paddle.device.set_device(device)
        with contextlib.redirect_stdout(None):
            self.model.to(device)

    def model_call(self, batch, fn: Callable, signature_fn: Optional[Callable]) -> Dict:
        if isinstance(batch, Dict) and not self.wo_auto_param_call:
            return auto_param_call(fn, batch, signature_fn=signature_fn)
        else:
            return fn(batch)

    def get_model_call_fn(self, fn: str) -> Tuple:
        if hasattr(self.model, fn):
            fn = getattr(self.model, fn)
            if not callable(fn):
                raise RuntimeError(f"The `{fn}` attribute is not `Callable`.")
            logger.debug(f'Use {_get_fun_msg(fn, with_fp=False)}...')
            return fn, None
        elif fn in {"train_step", "evaluate_step"}:
            logger.debug(f'Use {_get_fun_msg(self.model.forward, with_fp=False)}...')
            return self.model, self.model.forward
        else:
            raise RuntimeError(f"There is no `{fn}` method in your {type(self.model)}.")

    def set_dist_repro_dataloader(self, dataloader, dist: Union[str, ReproducibleBatchSampler, ReproducibleSampler]=None,
                                  reproducible: bool = False):

        # 暂时不支持iterableDataset
        assert dataloader.dataset_kind != _DatasetKind.ITER, \
                    "FastNLP does not support `IteratorDataset` now."
        # 如果 dist 为 ReproducibleBatchSampler, ReproducibleIterator 说明是在断点重训时 driver.load_checkpoint 函数调用；
        if isinstance(dist, ReproducibleBatchSampler):
            return replace_batch_sampler(dataloader, dist)
        elif isinstance(dist, ReproducibleSampler):
            return replace_sampler(dataloader, dist)

        # 如果 dist 为 str 或者 None，说明是在 trainer 初试化时调用；
        args = self.get_dataloader_args(dataloader)
        if isinstance(args.batch_sampler, ReproducibleBatchSampler):
            batch_sampler = re_instantiate_sampler(args.batch_sampler)
            return replace_batch_sampler(dataloader, batch_sampler)
        elif isinstance(args.sampler, ReproducibleSampler):
            sampler = re_instantiate_sampler(args.sampler)
            return replace_sampler(dataloader, sampler)

        if reproducible:
            if type(args.batch_sampler) is PaddleBatchSampler:
                if type(args.sampler) is PaddleRandomSampler:
                    if isinstance(args.sampler, PaddleRandomSampler):
                        if getattr(args.sampler, '_num_samples', None) is None \
                                and getattr(args.sampler, 'replacements', False) is False \
                                and getattr(args.sampler, 'generator', None) is None:
                            # 如果本来就是随机的，并且没有定制，直接替换掉。
                            sampler = RandomSampler(args.sampler.data_source, shuffle=True)
                            logger.debug("Replace paddle RandomSampler into fastNLP RandomSampler.")
                            return replace_sampler(dataloader, sampler)
                elif type(args.sampler) is PaddleSequenialSampler:
                    # 需要替换为不要 shuffle 的。
                    sampler = RandomSampler(args.sampler.data_source, shuffle=False)
                    logger.debug("Replace paddle SequentialSampler into fastNLP RandomSampler.")
                    return replace_sampler(dataloader, sampler)
            batch_sampler = ReproduceBatchSampler(
                batch_sampler=args.batch_sampler,
                batch_size=args.batch_size,
                drop_last=args.drop_last
            )
            return replace_batch_sampler(dataloader, batch_sampler)
        else:
            return dataloader

    def unwrap_model(self):
        """
        :return: 训练使用的模型。
        """
        return self.model

    @property
    def data_device(self) -> str:
        """
        :return: 数据和模型所在的设备。
        """
        return self.model_device

    def is_distributed(self) -> bool:
        """
        :return 是否为分布式的 **Driver** ，在 ``PaddleSingleDriver`` 中，返回 ``False``。
        """
        return False
