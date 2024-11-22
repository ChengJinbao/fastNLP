import os
import argparse
import logging
from pathlib import Path

from typing import Union, Dict, List
from .torch_driver import TorchDriver
from .ddp import TorchDDPDriver
from .utils import _create_default_config, _DeepSpeedWrappingModel
from fastNLP.core.utils import nullcontext
from fastNLP.core.log import logger
from fastNLP.envs import(
    FASTNLP_DISTRIBUTED_CHECK,
    FASTNLP_CHECKPOINT_FILENAME
)
from fastNLP.envs.imports import _NEED_IMPORT_TORCH, _NEED_IMPORT_DEEPSPEED

if _NEED_IMPORT_TORCH:
    import torch
    import torch.distributed as dist
    from torch.optim import Optimizer
    
if _NEED_IMPORT_DEEPSPEED:
    import deepspeed
    from deepspeed import DeepSpeedEngine, DeepSpeedOptimizer

__all__ = [
    "DeepSpeedDriver",
]

class DeepSpeedDriver(TorchDDPDriver):
    # TODO fp16 load_config
    def __init__(
        self,
        model,
        parallel_device: Union[List["torch.device"], "torch.device"],
        is_pull_by_torch_run = False,
        fp16: bool = False,
        **kwargs
    ):
        assert _NEED_IMPORT_DEEPSPEED, "Deepspeed is not imported."
        # assert not dist.is_initialized(), "DeepSpeedDriver does not support initialize distributed by user."
        TorchDriver.__init__(self, model=model, fp16=False, **kwargs)
        self.fp16 = fp16

        # 如果用户自己在外面初始化 DDP，那么其一定是通过 python -m torch.distributed.launch 拉起的；
        self.is_pull_by_torch_run = is_pull_by_torch_run
        self.parallel_device = parallel_device
        if not is_pull_by_torch_run and parallel_device is None:
            raise ValueError(
                "Parameter `parallel_device` can not be None when using `TorchDeepSpeedDriver`. This error is caused "
                "when your value of parameter `device` is `None` in your `Trainer` instance.")

        # 注意我们在 initialize_torch_driver 中的逻辑就是如果是 is_pull_by_torch_run，那么我们就直接把 parallel_device 置为当前进程的gpu；
        if is_pull_by_torch_run:
            self.model_device = parallel_device
        else:
            # 我们的 model_device 一定是 torch.device，而不是一个 list；
            self.model_device = parallel_device[self.local_rank]

        # 如果用户自己在外面初始化了 deepspeed；
        self.outside_ddp = False
        if dist.is_initialized() and FASTNLP_DISTRIBUTED_CHECK not in os.environ and \
                "fastnlp_torch_launch_not_ddp" not in os.environ:
            # 如果用户自己在外面初始化了 deepspeed，那么我们要求用户传入的模型一定是已经由 DeepSpeedEngine 包裹后的模型；
            if not isinstance(model, DeepSpeedEngine):
                raise RuntimeError(
                    "It is not allowed to input a normal model instead of `DeepSpeedEngine` when"
                    "you initialize the ddp process out of our control.")

            self.outside_ddp = True
            self.config = model.config
            self.model_device = None

        self._data_device = kwargs.get("data_device", None)
        if isinstance(self._data_device, int):
            if self._data_device < 0:
                raise ValueError("Parameter `data_device` can not be smaller than 0.")
            _could_use_device_num = torch.cuda.device_count()
            if self._data_device >= _could_use_device_num:
                raise ValueError("The gpu device that parameter `device` specifies is not existed.")
            self._data_device = torch.device(f"cuda:{self._data_device}")
        elif isinstance(self._data_device, str):
            self._data_device = torch.device(self._data_device)
        elif self._data_device is not None and not isinstance(self._data_device, torch.device):
            raise ValueError("Parameter `device` is wrong type, please check our documentation for the right use.")

        self._master_port = None
        # world_size 表示的就是全局的显卡的数量；
        self.world_size = None  # int(os.environ.get("WORLD_SIZE"))  len(self.parallel_device)
        self.global_rank = 0

        self.output_from_new_proc = kwargs.get("output_from_new_proc", "only_error")
        assert isinstance(self.output_from_new_proc, str), "Parameter `output_from_new_proc` can only be `str` type."
        if self.output_from_new_proc not in {"all", "ignore", "only_error"}:
            os.makedirs(name=self.output_from_new_proc, exist_ok=True)
            self.output_from_new_proc = os.path.abspath(self.output_from_new_proc)

        self._has_setup = False  # 设置这一参数是因为 evaluator 中也会进行 setup 操作，但是显然是不需要的也不应该的；
        self._has_ddpwrapped = False  # 判断传入的模型是否经过 _has_ddpwrapped 包裹；
        self.accumulation_steps = kwargs.get("accumulation_steps", 1)
        # 获取 batch_size 以设置 train_micro_batch_size_per_gpu 参数
        train_dl = kwargs.get("train_dataloader", None)
        if train_dl is not None:
            self.train_micro_batch_size = self.get_dataloader_args(train_dl).batch_size
        else:
            logger.warning("No `train_dataloader` found, and we will set `train_micro_batch_size_per_gpu`"
                        "to 1 for deepspeed configuration.")
            self.train_micro_batch_size = 1

        self._ds_kwargs = kwargs.get("deepspeed_kwargs", {})
        self.strategy = self._ds_kwargs.get("strategy", "deepspeed")
        deepspeed_logging_level = self._ds_kwargs.get("logging_level", logging.ERROR)
        deepspeed.utils.logging.logger.setLevel(deepspeed_logging_level)

    @staticmethod
    def _check_optimizer_legality(optimizers):
        for each_optimizer in optimizers:
            if not isinstance(each_optimizer, (Optimizer, DeepSpeedOptimizer)):
                raise TypeError(f"Each optimizer of parameter `optimizers` should be 'Optimizer' or "
                                f"'DeepSpeedOptimizer'type, not {type(each_optimizer)}.")

    def setup(self):
        r"""
        准备分布式环境，该函数主要做以下两件事情：

            1. 开启多进程，每个 gpu 设备对应单独的一个进程；
            2. 每个进程将模型迁移到自己对应的 ``gpu`` 设备上；然后使用 ``DistributedDataParallel`` 包裹模型；
        """
        if len(self.optimizers) != 1:
            raise ValueError("Multi optimizers is not supported for `DeepSpeedDriver` right now.")
        if self._has_setup:
            return
        self._has_setup = True
        self.setup_config()
        # 如果用户需要使用多机模式，那么一定进入到这里；
        if self.is_pull_by_torch_run:
            if self.outside_ddp:
                self.world_size = dist.get_world_size()
                self.global_rank = dist.get_rank()
            else:
                # dist.get_world_size() 只能在 dist.init_process_group 初始化之后进行调用；
                self.world_size = int(os.environ.get("WORLD_SIZE"))
                self.global_rank = int(os.environ.get("RANK"))
                logger.info(f"World size: {self.world_size}, Global rank: {self.global_rank}")

                if not dist.is_initialized():
                    deepspeed.init_distributed("nccl", distributed_port=self.master_port)

                os.environ["fastnlp_torch_launch_not_ddp"] = "yes"

        # 进入到这里的情况时：
        # dist.is_initialized 一定为 False；
        # 一定是单机；
        # self.parallel_device 一定是 List[torch.device]；
        else:
            if not dist.is_initialized():
                # 这里主要的问题在于要区分 rank0 和其它 rank 的情况；
                self.world_size = len(self.parallel_device)
                self.open_subprocess()
                self.global_rank = self.local_rank  # rank 一定是通过环境变量去获取的；
                deepspeed.init_distributed("nccl", distributed_port=self.master_port)
            # 用户在这个 trainer 前面又初始化了一个 trainer，并且使用的是 TorchDDPDriver；
            else:
                # 如果 `dist.is_initialized() == True`，那么说明 TorchDDPDriver 在之前已经初始化并且已经 setup 过一次，那么我们需要保证现在
                #  使用的（即之后的）TorchDDPDriver 的设置和第一个 TorchDDPDriver 是完全一样的；
                pre_num_processes = int(os.environ[FASTNLP_DISTRIBUTED_CHECK])
                if pre_num_processes != len(self.parallel_device):
                    raise RuntimeError(
                        "Notice you are using `TorchDDPDriver` after one instantiated `TorchDDPDriver`, it is not"
                        "allowed that your second `TorchDDPDriver` has a new setting of parameters "
                        "`num_nodes` and `num_processes`.")
                self.world_size = dist.get_world_size()
                self.global_rank = dist.get_rank()

        if not self.outside_ddp:
            torch.cuda.set_device(self.model_device)
            # TODO 模型过大的话应该会导致显存溢出，但是不加的话显存会占用rank对应的设备
            # lightning里在之前通过broadcast_list广播了log_dir所以没有这种情况
            self.model.to(self.model_device)
            self.configure_ddp()

        self.barrier()
        # 初始化 self._pids，从而使得每一个进程都能接受到 rank0 的 send 操作；
        self._pids = [torch.tensor(0, dtype=torch.int).to(self.data_device) for _ in range(dist.get_world_size())]
        dist.all_gather(self._pids, torch.tensor(os.getpid(), dtype=torch.int).to(self.data_device))
        local_world_size = int(os.environ.get("LOCAL_WORLD_SIZE")) if "LOCAL_WORLD_SIZE" in os.environ else None
        if local_world_size is None:
            local_world_size = torch.tensor(int(os.environ.get("LOCAL_RANK")), dtype=torch.int).to(self.data_device)
            dist.all_reduce(local_world_size, op=dist.ReduceOp.MAX)
            local_world_size = local_world_size.tolist() + 1

        node_rank = self.global_rank // local_world_size
        self._pids = self._pids[node_rank * local_world_size: (node_rank + 1) * local_world_size]
        self._pids = self.tensor_to_numeric(self._pids)

    def configure_ddp(self):
        
        # 设置 deepspeed
        if not isinstance(self.model, DeepSpeedEngine):
            model=_DeepSpeedWrappingModel(self.model, self.fp16)
            model_parameters = filter(lambda p: p.requires_grad, model.parameters())
            self.model, ds_optimizer, _, _ = deepspeed.initialize(
                args=argparse.Namespace(device_rank=self.model_device.index),
                model=model,
                optimizer=self.optimizers[0],
                model_parameters=model_parameters,
                config=self.config,
                dist_init_required=False
            )
            self._optimizers = [ds_optimizer]

            if self.config.get("activation_checkpointing"):
                checkpoint_config = self.config["activation_checkpointing"]
                deepspeed.checkpointing.configure(
                    mpu_=None,
                    partition_activations=checkpoint_config.get("partition_activations"),
                    contiguous_checkpointing=checkpoint_config.get("contiguous_memory_optimization"),
                    checkpoint_in_cpu=checkpoint_config.get("cpu_checkpointing"),
                    profile=checkpoint_config.get("profile"),
                )

            self._has_ddpwrapped = True

    def setup_config(self):

        self.config = self._ds_kwargs.get("config")
        if self.config is not None:
            logger.warning("Notice that you have defined a configuration for deepspeed and parameters like"
                        "`optimizers`, `strategy` and `fp16` may not take effects.")
            return

        if self.strategy == "deepspeed":
            self.config = _create_default_config(stage=2)
        elif self.strategy == "deepspeed_stage_1":
            self.config = _create_default_config(stage=1)
        elif self.strategy == "deepspeed_stage_2":
            self.config = _create_default_config(stage=2)
        elif self.strategy == "deepspeed_stage_2_offload":
            self.config = _create_default_config(stage=2, offload_optimizer=True)
        elif self.strategy == "deepspeed_stage_3":
            self.config = _create_default_config(stage=3)
        elif self.strategy == "deepspeed_stage_3_offload":
            self.config = _create_default_config(
                stage=3,
                offload_optimizer=True,
                offload_parameters=True,
            )
        elif self.strategy == "deepspeed_stage_3_offload_nvme":
            self.config = _create_default_config(
                stage=3,
                offload_optimizer=True,
                offload_parameters=True,
                remote_device="nvme",
                offload_params_device="nvme",
                offload_optimizer_device="nvme",
            )
        else:
            raise ValueError(f"Unknown deepspeed strategy {self.strategy}.")

        # 设置成 max_int 防止 deepspeed 的输出干扰 fastnlp 的输出
        self.config.setdefault("steps_per_print", 2147483647)
        self.config["gradient_accumulation_steps"] = self.accumulation_steps
        self.config.setdefault("train_micro_batch_size_per_gpu", self.train_micro_batch_size)

        if self.fp16:
            if "fp16" not in self.config:
                # FP16 is a DeepSpeed standalone AMP implementation
                logger.debug("Enabling DeepSpeed FP16.")
                # TODO 这部分是否可以像 pytorch-lightning 那样给用户定制
                self.config["fp16"] = {
                    "enabled": True,
                    "loss_scale": 0,
                    "initial_scale_power": True,
                    "loss_scale_window": 1000,
                    "hysteresis": 2,
                    "min_loss_scale": 1,
                }
            elif "amp" not in self.config:
                logger.debug("Enabling DeepSpeed APEX Implementation.")
                self.config["amp"] = {"enabled": True, "opt_level": "O1"}

    def zero_grad(self):
        # DeepSpeedEngine.step 包含了 zero_grad 功能
        pass

    def backward(self, loss):
        self.model.backward(loss)

    def step(self):
        self.model.step()

    def get_model_no_sync_context(self):
        r"""
        :return: 返回一个 ``context`` 上下文环境，用于关闭各个进程之间的同步；在 ``deepspeed`` 中，返回一个空的上下文
        """
        # 注意此时的 model 是 "DistributedDataParallel" 对象；
        return nullcontext

    def save_model(self, filepath: Union[str, Path], only_state_dict: bool = False, **kwargs):
        """
        保存当前 driver 的模型到 folder 下。

        :param filepath: 保存到哪个文件夹；
        :param only_state_dict: 是否只保存权重；
        :return:
        """
        # deepspeed engine 要求在每个 rank 都调用 save_checkpoint，故去掉了 rank_zero_call 装饰器
        if self.stage_3:
            logger.rank_zero_warning(
                "When saving the DeepSpeed Stage 3 checkpoint, "
                "each worker will save a shard of the checkpoint within a directory. "
                # TODO check一下
                # "If a single file is required after training, "
                # "see https://pytorch-lightning.readthedocs.io/en/latest/advanced/advanced_gpu.html#"
                # "deepspeed-zero-stage-3-single-file for instructions."
            )
        if not only_state_dict:
            logger.rank_zero_warning("Only saving state dict is not allowed for `DeepSpeedDriver`. We will save its "
                        "checkpoint for you instead.")
        self.model.save_checkpoint(filepath, **kwargs)

    def load_model(self, filepath: Union[Path, str], only_state_dict: bool = False, **kwargs):
        """
        从 folder 中加载权重并赋值到当前 driver 的模型上。

        :param filepath: 加载权重或模型的路径
        :param load_state_dict: 保存的内容是否只是权重。
        :param kwargs:
        :return:
        """
        if not only_state_dict:
            logger.warning("Only loading state dict is not allowed for `DeepSpeedDriver`. We will load its "
                        "checkpoint for you instead.")
        self.model.load_checkpoint(filepath, **kwargs)

    def save_checkpoint(self, folder: Path, states: Dict, dataloader, only_state_dict: bool = True, should_save_model: bool = True, **kwargs):
        # deepspeed engine 要求在每个 rank 都调用 save_checkpoint，故去掉了 rank_zero_call 装饰器
        # 1. 保存 sampler 的状态
        num_consumed_batches = states.pop('num_consumed_batches')
        states['sampler_states'] = self.get_sampler_state(dataloader, num_consumed_batches)

        # 2. 保存模型的状态；
        if not should_save_model:
            logger.rank_zero_warning("Saving checkpoint without model is not allowed for `DeepSpeedDriver`, "
                                    "so we will still save the model for you.")

        self.model.save_checkpoint(Path(folder).joinpath(FASTNLP_CHECKPOINT_FILENAME),
                                    client_state=states)

    def load_checkpoint(self, folder: Path, dataloader, only_state_dict: bool = True, should_load_model: bool = True, **kwargs) -> Dict:
        # 1. 加载模型状态；
        if not should_load_model:
            logger.rank_zero_warning("Loading checkpoint without model is not allowed for `DeepSpeedDriver`, "
                                    "so we will still load the model for you.")
        load_path, states = self.model.load_checkpoint(folder.joinpath(FASTNLP_CHECKPOINT_FILENAME))
        if load_path is None:
            raise RuntimeError(f"Failed to load checkpoint from path: {str(folder)}")

        # 2.恢复 sampler 的状态
        sampler_states = states.pop('sampler_states')
        states_ret = self.load_sampler_state(dataloader, sampler_states)
        states.update(states_ret)

        return states

    @property
    def stage_3(self) -> bool:
        return self.config.get("zero_optimization") and self.config.get("zero_optimization").get("stage") == 3