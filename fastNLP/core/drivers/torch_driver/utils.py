import os

from typing import Any, Dict, Optional, Union
from enum import IntEnum
import contextlib
import random
import numpy as np
import inspect

from fastNLP.envs.imports import _NEED_IMPORT_TORCH
from fastNLP.envs.utils import get_global_seed
from fastNLP.envs import (
    get_global_rank,
    FASTNLP_BACKEND_LAUNCH,
    FASTNLP_GLOBAL_SEED,
)
from fastNLP.core.samplers import re_instantiate_sampler, ReproducibleBatchSampler, ReproducibleSampler
from fastNLP.core.utils import auto_param_call, apply_to_collection
from fastNLP.core.log import logger

if _NEED_IMPORT_TORCH:
    import torch
    # import torch.nn as nn
    from torch.nn import Module
    from torch.utils.data import DataLoader
    from torch.utils.data import RandomSampler as TorchRandomSampler
    from torch.utils.data import SequentialSampler as TorchSequentialSampler
    from torch.utils.data import BatchSampler as TorchBatchSampler

else:
    from fastNLP.core.utils.dummy_class import DummyClass as Module


__all__ = [
    'torch_seed_everything',
    'optimizer_state_to_device'
]

def torch_seed_everything(seed: int = None, add_global_rank_to_seed: bool = True) -> int:
    r"""
    为 **torch**、**numpy**、**python.random** 伪随机数生成器设置种子。

    :param seed: 全局随机状态的整数值种子。如果为 ``None`` 则会根据时间戳生成一个种子。
    :param add_global_rank_to_seed: 在分布式训练中，是否在不同 **rank** 中使用不同的随机数。
        当设置为 ``True`` 时，**fastNLP** 会将种子加上当前的 ``global_rank``。
    """
    max_seed_value = np.iinfo(np.uint32).max
    min_seed_value = np.iinfo(np.uint32).min

    if seed is None:
        if os.getenv(FASTNLP_BACKEND_LAUNCH) == "1":
            seed = 42
        else:
            seed = get_global_seed()
        logger.info(f"'FASTNLP_GLOBAL_SEED' is set to {seed} automatically.")
    if not isinstance(seed, int):
        seed = int(seed)

    if not (min_seed_value <= seed <= max_seed_value):
        logger.rank_zero_warning("Your seed value is too big or too small for numpy, we will choose a random seed for you.")
        seed %= max_seed_value

    os.environ[FASTNLP_GLOBAL_SEED] = f"{seed}"
    if add_global_rank_to_seed:
        seed += get_global_rank()

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    return seed


class ForwardState(IntEnum):
    TRAIN = 0
    VALIDATE = 1
    TEST = 2
    PREDICT = 3


class _DDPWrappingModel(Module):
    """
    该函数用于 DDP 训练时处理用户自己定制的 train_step 等函数；
    之所以要使用这一额外的包裹模型，是因为在使用 DDP 时，必须使用 DistributedDataParallel 的 forward 函数才能实现正常的运行；
    另一方面，我们要求用户在使用我们的框架时，需要针对不用的模式实现不同的处理函数，例如 'train_step', 'evaluate_step' 等；
    然而，当使用 DistributedDataParallel 包裹 model 后，模型看不见其除了 forward 之外的方法；并且当我们尝试在训练过程中主动提取
    `model = model.module`，这同样会导致错误，会使得每一个gpu上的模型参数不同；

    因此出于以上考虑，我们实现了这一函数；
    对于更详细的解释，可以参考 'pytorch_lightning' 的 ddp 的设计；
    """

    def __init__(self, model: Module):
        super(_DDPWrappingModel, self).__init__()
        self.model = model

    def forward(self, batch, **kwargs) -> Dict:
        """
        pytorch lightning 实现了先 unwrapping_model 的操作，但是感觉对于我们来说没有什么必须要，先写个注释放这里，之后有需求了再看；
        """
        fn = kwargs.pop("fastnlp_fn")
        signature_fn = kwargs.pop("fastnlp_signature_fn")
        wo_auto_param_call = kwargs.pop("wo_auto_param_call")

        if isinstance(batch, Dict) and not wo_auto_param_call:
            return auto_param_call(fn, batch, signature_fn=signature_fn)
        else:
            return fn(batch)

class _DeepSpeedWrappingModel(_DDPWrappingModel):
    """
    继承 ``_DDPWrappingModel``，区别在于进行 forward 之前先将 float 数据转换为 float16
    """

    def __init__(self, model: Module, fp16):
        super(_DeepSpeedWrappingModel, self).__init__(model)
        self.fp16 = fp16

    def forward(self, batch, **kwargs):
        if self.fp16:
            batch = self._move_float_tensors_to_half(batch)

        return super().forward(batch, **kwargs)

    @staticmethod
    def batch_to(data):
        return data.half()

    def _move_float_tensors_to_half(self, batch: Any):
        batch = apply_to_collection(batch, (torch.FloatTensor, torch.cuda.FloatTensor), function=self.batch_to)
        return batch


class DummyGradScaler:
    """
    用于Dummy pytorch的GradScaler对象，防止重复写大量的if判断

    """

    def __init__(self, *args, **kwargs):
        pass

    def get_scale(self):
        return 1.0

    def is_enabled(self):
        return False

    def scale(self, outputs):
        return outputs

    def step(self, optimizer, *args, **kwargs):
        optimizer.step(*args, **kwargs)

    def update(self, new_scale=None):
        pass

    def unscale_(self, optimizer):
        pass

    def load_state_dict(self, state_dict):
        pass

    def state_dict(self):
        return {}


def _build_fp16_env(dummy=False):
    if dummy:
        autocast = contextlib.ExitStack
        GradScaler = DummyGradScaler
    else:
        if not torch.cuda.is_available():
            raise RuntimeError("Pytorch is not installed in gpu version, please use device='cpu'.")
        if torch.cuda.get_device_capability(0)[0] < 7:
            logger.rank_zero_warning(
                "NOTE: your device does NOT support faster training with fp16, "
                "please switch to FP32 which is likely to be faster"
            )
        try:
            from torch.cuda.amp import autocast, GradScaler
        except ImportError:
            raise RuntimeError("torch version too low (less than 1.6)")
    return autocast, GradScaler


def replace_sampler(dataloader: "DataLoader", sampler):
    r"""
    替换 sampler （初始化一个新的 dataloader 的逻辑在于）：

    用户可能继承了 dataloader，定制了自己的 dataloader 类，这也是我们为什么先 `inspect.signature(dataloader)` 而不是直接
    `inspect.signature(DataLoader)` 的原因，因此同时注意到我们在外层重新初始化一个 dataloader 时也是使用的用户传进来的 dataloader
    的类，而不是直接的 DataLoader；

    如果需要定制自己的 dataloader，保证以下两点：

        1. 在 __init__ 方法中加入 **kwargs，这是为了方便我们将 sampler 插入到具体的 DataLoader 的构造中；
        2. 在 __init__ 方法中出现的参数，请务必挂为同样名字的实例属性，例如 self.one_arg_name = one_arg_name，这是因为我们只能通过属性
        来获取实际的参数的值；

     """

    # 拿到实例属性；
    instance_attrs = {k: v for k, v in vars(dataloader).items() if not k.startswith('_')}

    # 'multiprocessing_context' 是 user-defined function;
    if getattr(dataloader, 'multiprocessing_context', None) is not None:
        instance_attrs["multiprocessing_context"] = dataloader.multiprocessing_context

    # 拿到 dataloader '__init__' 函数的默认函数签名；
    init_params = dict(inspect.signature(dataloader.__init__).parameters)

    # 防止用户的 DataLoader 是继承了 pytorch 的 DataLoader，然后还是使用了 **kwargs 的方式对父类传参数
    has_variadic_kwargs = any(v.kind is v.VAR_KEYWORD for k, v in init_params.items())
    if has_variadic_kwargs and isinstance(dataloader, DataLoader):
        # 防止用户写入了 super().__init__(**kwargs)
        for key, value in dict(inspect.signature(DataLoader.__init__).parameters).items():
            if key not in init_params and key != 'self':
                init_params[key] = value

    # 如果初始化dataloader所使用的参数不是默认值，那么我们需要将其记录下来用于重新初始化时设置；
    non_default_params = {name for name, p in init_params.items() if
                          name in instance_attrs and p.default != instance_attrs[name]}
    # add `dataset` as it might have been replaced with `*args`
    non_default_params.add("dataset")

    reconstruct_args = {k: v for k, v in instance_attrs.items() if k in non_default_params}
    if isinstance(dataloader, DataLoader):
        reconstruct_args.update({"sampler": sampler, "shuffle": False, "batch_sampler": None})

    batch_sampler = getattr(dataloader, "batch_sampler")
    if batch_sampler is not None and isinstance(batch_sampler, ReproducibleBatchSampler):
        raise RuntimeError("It should not be running here, please report a bug to us.")

    required_args = {
        p.name
        for p in init_params.values()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
           and p.default is p.empty
           and p.name not in reconstruct_args
    }

    # 在 attribute 中没有找到这些参数，导致了没有办法重新初始化
    if required_args:
        required_args = sorted(required_args)
        dataloader_self_name = dataloader.__class__.__name__
        raise Exception(
            f"Need to inject arguments {required_args} into the __init__ of `{dataloader_self_name}`. "
            f"But they are not found in the attribute of `{dataloader_self_name}`, fastNLP cannot determine its "
            f"value when try to reinitialize `{dataloader_self_name}`, please add `{required_args}` to be "
            f"`{dataloader_self_name}`'s attribute."
        )

    # 这种错误针对的是传入的 dataloader 不是直接的 DataLoader，而是定制了 DataLoader，但是 __init__ 中没有 **kwargs；
    if not has_variadic_kwargs:
        # the dataloader signature does not allow keyword arguments that need to be passed
        missing_kwargs = reconstruct_args.keys() - init_params.keys()
        if missing_kwargs:
            missing_kwargs = sorted(missing_kwargs)
            dataloader_self_name = dataloader.__class__.__name__
            raise Exception(
                f"The parameter:{missing_kwargs} needed to reinitialize `{dataloader_self_name}` is not found."
            )
        # 如果没有kwargs，则保证一下只传入需要的参数
        if not isinstance(dataloader, DataLoader):
            reconstruct_args = {key:value for key,value in reconstruct_args.items() if key in init_params}

    return type(dataloader)(**reconstruct_args)


def replace_batch_sampler(dataloader, new_batch_sampler):
    r"""
    替换一个 dataloader 的 batch_sampler；
    """
    params_keys = [k for k in dataloader.__dict__.keys() if not k.startswith("_")]
    for k in ["batch_size", "sampler", "drop_last", "batch_sampler", "dataset_kind"]:
        if k in params_keys:
            params_keys.remove(k)
    params = {k: getattr(dataloader, k) for k in params_keys}
    params["batch_sampler"] = new_batch_sampler

    if not isinstance(dataloader, DataLoader):
        init_params = dict(inspect.signature(dataloader.__init__).parameters)
        has_variadic_kwargs = any(v.kind is v.VAR_KEYWORD for k, v in init_params.items())
        if not has_variadic_kwargs:
            params = {key:value for key,value in params.items() if key in init_params}

    return type(dataloader)(**params)


def optimizer_state_to_device(state, device):
    r"""
    将一个 ``optimizer`` 的 ``state_dict`` 迁移到对应的设备。

    :param state: ``optimzier.state_dict()``。
    :param device: 要迁移到的目的设备。
    :return: 迁移后的新的 state_dict。
    """
    new_state = {}
    for name, param in state.items():
        if isinstance(param, dict):
            new_state[name] = optimizer_state_to_device(param, device)
        elif isinstance(param, torch.Tensor):
            new_state[name] = param.to(device).clone()
        else:
            new_state[name] = param
    return new_state


def _check_dataloader_args_for_distributed(args, controller='Trainer'):
    """
    检查 dataloader 的 sampler 情况，如果用户替换了自己定制的 sampler ，为了防止
    在分布式训练中出现错误会报错。
    """
    error_flag = (type(args.sampler) not in {TorchRandomSampler, TorchSequentialSampler})
    if controller == 'Trainer':
        mode = 'training'
        substitution = 'fastNLP.RandomSampler'
        error_flag = (type(args.batch_sampler) != TorchBatchSampler) or error_flag
    else: # Evaluator
        mode = 'evaluation'
        substitution = 'fastNLP.UnrepeatedSequentialSampler'
    if error_flag:
        raise TypeError(f"Using customized ``batch_sampler`` or ``sampler`` for distributed {mode} may cause "
                        f"unpredictable problems, because fastNLP will substitute the dataloader's sampler into "
                        f"``{substitution}``. The customized sampler should set for distributed running  "
                        f"before initializing ``{controller}`` , and then set the "
                        f"parameter ``use_dist_sampler`` of ``{controller}`` to ``False``."
                        f"\n Current batch_sampler: {type(args.batch_sampler)}"
                        f"\n Current sampler: {type(args.sampler)}")

def _create_default_config(
    zero_optimization: bool = True,
    zero_allow_untested_optimizer: bool = True,
    logging_batch_size_per_gpu: Union[str, int] = "auto",
    partition_activations: bool = False,
    cpu_checkpointing: bool = False,
    contiguous_memory_optimization: bool = False,
    synchronize_checkpoint_boundary: bool = False,
    offload_optimizer: bool = False,
    offload_parameters: bool = False,
    offload_params_device: str = "cpu",
    nvme_path: str = "/local_nvme",
    params_buffer_count: int = 5,
    params_buffer_size: int = 100_000_000,
    max_in_cpu: int = 1_000_000_000,
    offload_optimizer_device: str = "cpu",
    optimizer_buffer_count: int = 4,
    pin_memory: bool = False,
    block_size: int = 1048576,
    queue_depth: int = 8,
    single_submit: bool = False,
    overlap_events: bool = True,
    thread_count: int = 1,
    stage: int = 2,
    contiguous_gradients: bool = True,
    overlap_comm: bool = True,
    allgather_partitions: bool = True,
    reduce_scatter: bool = True,
    allgather_bucket_size: int = 200_000_000,
    reduce_bucket_size: int = 200_000_000,
    sub_group_size: int = 1_000_000_000_000,
) -> Dict:
    cfg = {
        "activation_checkpointing": {
            "partition_activations": partition_activations,
            "cpu_checkpointing": cpu_checkpointing,
            "contiguous_memory_optimization": contiguous_memory_optimization,
            "synchronize_checkpoint_boundary": synchronize_checkpoint_boundary,
        },
        "aio": {
            "block_size": block_size,
            "queue_depth": queue_depth,
            "single_submit": single_submit,
            "overlap_events": overlap_events,
            "thread_count": thread_count,
        },
    }
    zero_kwargs = {
        "stage": stage,
        "contiguous_gradients": contiguous_gradients,
        "overlap_comm": overlap_comm,
        "allgather_partitions": allgather_partitions,
        "reduce_scatter": reduce_scatter,
        "allgather_bucket_size": allgather_bucket_size,
        "reduce_bucket_size": reduce_bucket_size,
        "sub_group_size": sub_group_size,
    }
    if zero_optimization:
        zero_config = zero_kwargs

        if offload_optimizer:
            zero_config["offload_optimizer"] = {
                "device": offload_optimizer_device,
                "nvme_path": nvme_path,
                "buffer_count": optimizer_buffer_count,
                "pin_memory": pin_memory,
            }
        if offload_parameters:
            zero_config["offload_param"] = {
                "device": offload_params_device,
                "nvme_path": nvme_path,
                "buffer_count": params_buffer_count,
                "buffer_size": params_buffer_size,
                "max_in_cpu": max_in_cpu,
                "pin_memory": pin_memory,
            }
        cfg = {
            "zero_allow_untested_optimizer": zero_allow_untested_optimizer,
            "zero_optimization": zero_config,
            **cfg,
        }
    if logging_batch_size_per_gpu != "auto":
        cfg = {"train_micro_batch_size_per_gpu": logging_batch_size_per_gpu, **cfg}
    return cfg