import os
from typing import Dict, Union, Callable, Tuple, Optional
from fastNLP.envs.imports import _NEED_IMPORT_TORCH

if _NEED_IMPORT_TORCH:
    import torch
    from torch.nn import DataParallel
    from torch.nn.parallel import DistributedDataParallel
    from torch.utils.data import RandomSampler as TorchRandomSampler
    from torch.utils.data import SequentialSampler as TorchSequentialSampler
    from torch.utils.data import BatchSampler as TorchBatchSampler

__all__ = [
    'TorchSingleDriver'
]

from .torch_driver import TorchDriver
from fastNLP.core.drivers.torch_driver.utils import replace_sampler, replace_batch_sampler
from fastNLP.core.utils import auto_param_call
from fastNLP.core.utils.utils import _get_fun_msg
from fastNLP.core.samplers import ReproducibleBatchSampler, ReproducibleSampler, re_instantiate_sampler, \
    ReproduceBatchSampler
from fastNLP.core.samplers import RandomSampler
from fastNLP.core.log import logger


class TorchSingleDriver(TorchDriver):
    r"""
    ``TorchSingleDriver`` 是用于 cpu 和 单卡 gpu 运算的 ``driver``。

    .. note::

        如果您希望使用 ``DataParallel`` 来训练您的模型，您应当自己在 ``Trainer`` 初始化之前初始化好 ``DataParallel``，然后将其传入 ``Trainer`` 中。

    :param model: 传入给 ``Trainer`` 的 ``model`` 参数
    :param device: torch.device，当前进程所使用的设备
    :param fp16: 是否开启 fp16
    :param torch_kwargs:
        * *set_grad_to_none* -- 是否在训练过程中在每一次 optimizer 更新后将 grad 置为 ``None``
        * *non_blocking* -- 表示用于 :meth:`torch.Tensor.to` 方法的参数 non_blocking
        * *gradscaler_kwargs* -- 用于 ``fp16=True`` 时，提供给 :class:`torch.amp.cuda.GradScaler` 的参数
    :kwargs:
        * *wo_auto_param_call* (``bool``) -- 是否关闭在训练时调用我们的 ``auto_param_call`` 函数来自动匹配 batch 和前向函数的参数的行为

        .. note::

            关于该参数的详细说明，请参见 :class:`~fastNLP.core.controllers.Trainer` 中的描述；函数 ``auto_param_call`` 详见 :func:`fastNLP.core.utils.auto_param_call`。
    """

    def __init__(self, model, device: "torch.device", fp16: bool = False, torch_kwargs: Dict = None, **kwargs):
        if isinstance(model, DistributedDataParallel):
            raise ValueError("`DistributedDataParallel` is not supported in `TorchSingleDriver`")

        cuda_visible_devices = os.environ.get("CUDA_VISIBLE_DEVICES", None)
        if cuda_visible_devices == "":
            device = torch.device("cpu")
            logger.info("You have set `CUDA_VISIBLE_DEVICES` to '' in system environment variable, and we are gonna to"
                        "use `cpu` instead of `gpu` device.")

        super(TorchSingleDriver, self).__init__(model, fp16=fp16, torch_kwargs=torch_kwargs, **kwargs)

        if device is None:
            logger.debug("device is not set, fastNLP will try to automatically get it.")
            try:
                device = next(model.parameters()).device
                assert isinstance(device, torch.device)
            except:
                raise ValueError("fastNLP cannot get device automatically, please set device explicitly.")

        self.model_device = device

        self.local_rank = 0
        self.global_rank = 0
        self.world_size = 1

    def setup(self):
        r"""
        将模型迁移到相应的设备上。
        """
        if self.model_device is not None:
            self.model.to(self.model_device)

    def model_call(self, batch, fn: Callable, signature_fn: Optional[Callable]) -> Dict:
        if isinstance(batch, Dict) and not self.wo_auto_param_call:
            return auto_param_call(fn, batch, signature_fn=signature_fn)
        else:
            return fn(batch)

    def get_model_call_fn(self, fn: str) -> Tuple:
        if isinstance(self.model, DataParallel):
            model = self.unwrap_model()
            if hasattr(model, fn):
                logger.warning("Notice your model is a `DataParallel` model. And your model also implements the "
                               f"`{fn}` method, which we can not call actually, we will"
                               " call `forward` function instead of `train_step` and you should note that.")

            elif fn not in {"train_step", "evaluate_step"}:
                raise RuntimeError(f"There is no `{fn}` method in your model. And also notice that your model is a "
                                   f"`DataParallel` model, which means that we will only call model.forward function "
                                   f"when we are in forward propagation.")

            return self.model, model.forward
        else:
            # TODO 这种直接调用模型某个接口的方法无法触发hook，也许需要做一个warning，如果用户有钩子，提醒他train_step无法触发。
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

    def set_dist_repro_dataloader(self, dataloader,
                                  dist: Union[str, ReproducibleBatchSampler, ReproducibleSampler] = None,
                                  reproducible: bool = False):

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
            if type(args.batch_sampler) is TorchBatchSampler:
                if type(args.sampler) is TorchRandomSampler:
                    if getattr(args.sampler, '_num_samples', None) is None \
                            and getattr(args.sampler, 'replacements', False) is False \
                            and getattr(args.sampler, 'generator', None) is None:
                        # 如果本来就是随机的，并且没有定制，直接替换掉吧。
                        sampler = RandomSampler(args.sampler.data_source, shuffle=True)
                        logger.debug("Replace torch RandomSampler into fastNLP RandomSampler.")
                        return replace_sampler(dataloader, sampler)
                elif type(args.sampler) is TorchSequentialSampler:
                    # 需要替换为不要 shuffle 的。
                    sampler = RandomSampler(args.sampler.data_source, shuffle=False)
                    logger.debug("Replace torch SequentialSampler into fastNLP RandomSampler.")
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
        r"""
        :return: 原本的模型，该函数可以取出被 ``DataParallel`` 包裹的模型
        """
        if isinstance(self.model, torch.nn.DataParallel) or \
                isinstance(self.model, torch.nn.parallel.DistributedDataParallel):
            return self.model.module
        else:
            return self.model

    @property
    def data_device(self):
        r"""
        数据和模型所在的设备
        """
        return self.model_device

    def is_distributed(self):
        r"""
        :return: 当前使用的 driver 是否是分布式的 driver，对于 ``TorchSingleDriver`` 来说直接返回 ``False``
        """
        return False
