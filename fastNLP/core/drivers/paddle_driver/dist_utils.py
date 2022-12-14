import io
import pickle
import os
from typing import Any, List

import numpy as np
from fastNLP.envs.imports import _NEED_IMPORT_PADDLE
from fastNLP.envs.env import FASTNLP_NO_SYNC
from fastNLP.core.utils import paddle_move_data_to_device

if _NEED_IMPORT_PADDLE:
    import paddle
    import paddle.distributed as dist
    from paddle.framework.io import (
        _is_state_dict,
        _build_saved_state_dict,
        _unpack_saved_dict,
        _pickle_save,
        _pack_loaded_dict,
        _ndarray_to_tensor,
        _parse_load_result,
    )

__all__ = []

def _validate_output_list_for_rank(my_rank, dst, gather_list):
    if dst == my_rank:
        if not gather_list:
            raise ValueError(
                "Argument ``gather_list`` must be specified on destination rank."
            )
    elif gather_list:
        raise ValueError(
            "Argument ``gather_list`` must NOT be specified "
            "on non-destination ranks."
        )

def paddle_pickle_dump(obj, stream, protocol):
    """
    Reference to `paddle.save`
    """
    if _is_state_dict(obj):
        saved_obj = _build_saved_state_dict(obj)
        saved_obj = _unpack_saved_dict(saved_obj, protocol)
        pickle.dump(saved_obj, stream, protocol=protocol)
    else:
        _pickle_save(obj, stream, protocol)

def paddle_pickle_load(stream):
    """
    Reference to `paddle.load`
    """
    load_result = pickle.load(stream)
    if isinstance(load_result, dict):
        load_result = _pack_loaded_dict(load_result)
        if "StructuredToParameterName@@" in load_result:

            for key in load_result["StructuredToParameterName@@"]:
                if isinstance(load_result[key], np.ndarray):
                    load_result[key] = _ndarray_to_tensor(
                        load_result[key], return_numpy=False)

            if "StructuredToParameterName@@" in load_result:
                del load_result["StructuredToParameterName@@"]
        else:
            load_result = _parse_load_result(load_result, return_numpy=False)

    else:
        load_result = _parse_load_result(load_result, return_numpy=False)

    return load_result

def _object_to_tensor(obj, device=None):
    f = io.BytesIO()
    paddle_pickle_dump(obj, f, protocol=2)
    byte_data = list(f.getvalue())
    byte_tensor = paddle.to_tensor(byte_data, dtype=paddle.int32)
    local_size = paddle.to_tensor([byte_tensor.numel()])
    if device is not None:
        byte_tensor = paddle_move_data_to_device(byte_tensor, device)
        local_size = paddle_move_data_to_device(local_size, device)
    return byte_tensor, local_size

def _tensor_to_object(tensor, tensor_size):
    buf = tensor.astype(paddle.uint8).detach().cpu().numpy().tobytes()[:tensor_size]
    return paddle_pickle_load(io.BytesIO(buf))

def fastnlp_paddle_gather_object(obj, dst=0, group=None):
    """
    ????????? rank gather ????????? dst rank ???

    Example::
        >>> # Assumes world_size of 3.
        >>> gather_objects = ["foo", 12, {1: 2}] # any picklable object
        >>> output = [None for _ in gather_objects]
        >>> fastnlp_paddle_gather_object(
                gather_objects[dist.get_rank()],
                output if dist.get_rank() == 0 else None,
                dst=0
            )
        >>> # On rank 0
        >>> output
        ['foo', 12, {1: 2}]

    :param obj: ??????????????? obj ???????????????????????? pickable ?????????
    :param dst: ????????? rank ???
    :param group: ????????? group ??????????????????
    :return: ??? dst ???????????? world_size ??? list???????????? rank 0???rank 1...??? obj
    """
    if int(os.environ.get(FASTNLP_NO_SYNC, '0')) == 2:
        return [obj]

    if dist.get_rank() == dst:
        object_gather_list = [None for _ in range(dist.get_world_size())]
    else:
        object_gather_list = None

    # if group is None:
        # TODO 2.2 ???????????? bug
        # group = dist.collective._get_global_group()

    if group is not None and not group.is_member():
        return

    # Ensure object_gather_list is specified appopriately.
    my_rank = dist.get_rank()
    _validate_output_list_for_rank(my_rank, dst, object_gather_list)
    # ?????? unpickle ?????????????????????????????? gpu ??????
    obj = paddle_move_data_to_device(obj, device="cpu")
    input_tensor, local_size = _object_to_tensor(obj)
    # ?????? paddle ??? group ????????? nccl
    input_tensor = paddle_move_data_to_device(input_tensor, device=paddle.device.get_device())
    local_size = paddle_move_data_to_device(local_size, device=paddle.device.get_device())

    # ??????????????? local_size?????????????????? size
    object_size_list = []
    dist.all_gather(object_size_list, local_size, group=group)
    max_object_size = int(max(object_size_list).item())  # type: ignore[type-var]
    input_tensor.reshape_(max_object_size)
    # TODO ??????????????? paddle ??????????????? torch.distributed.gather ?????????
    output_tensors = []
    dist.all_gather(output_tensors, input_tensor, group)
    if my_rank != dst:
        return
    for i, tensor in enumerate(output_tensors):
        tensor = tensor.astype(paddle.uint8)
        tensor_size = object_size_list[i]
        object_gather_list[i] = _tensor_to_object(tensor, tensor_size)

def send_recv_object(obj, src, cur_rank, device, group=None, use_calc_stream=True):
    # src rank send to all other ranks
    size = paddle_move_data_to_device(paddle.to_tensor([0]), device)

    if cur_rank == src:
        world_size = dist.get_world_size()
        tensor, size = _object_to_tensor(obj)
        tensor = tensor.to(device)
        size = size.to(device)

        # ???????????? obj ??? size ????????????
        dist.broadcast(size, src, group=group)
        for subrank in range(world_size):
            if subrank != src:
                dist.send(tensor=tensor, dst=subrank, group=group, use_calc_stream=use_calc_stream)
    else:
        dist.broadcast(size, src, group=group)
        tensor = paddle_move_data_to_device(paddle.to_tensor([0] * size), device)
        dist.recv(tensor=tensor, src=src, group=group, use_calc_stream=use_calc_stream)

    return _tensor_to_object(tensor.cpu(), size)

def fastnlp_paddle_all_gather(obj: Any, device=None, group=None) ->List:
    """
    ????????????????????????????????????????????????????????? all_gather ?????????????????? tensor ???????????????????????? pickle ????????????????????????????????????????????????

    example::

        >>> # rank 0
        >>> obj = {'a': 1, 'b':[1, 2], 'c':{'d': 1}}
        >>> # rank 1
        >>> obj = {'a': 1, 'b':[1, 2], 'c':{'d': 2}}
        >>> # after all_gather():
        >>> result = [
                {'a': 1, 'b':[1, 2], 'c':{'d': 1}},
                {'a': 1, 'b':[1, 2], 'c':{'d': 2}}
            ]

    :param obj: ????????????????????????????????? tensor ????????????????????????????????? tensor ????????????????????????????????????????????? tensor ????????????????????????
        ??????????????????????????????
    :param device: ???????????????????????????
    :param group:
    :return: ?????????????????? [obj0, obj1, ...]????????? obj_i ????????? i ??? rank ?????? obj ???
    """
    if int(os.environ.get(FASTNLP_NO_SYNC, '0')) == 2:
        return [obj]

    # if group is None:
        # TODO 2.2 ???????????? bug
        # group = dist.collective._get_global_group()
    if isinstance(obj, paddle.Tensor):
        objs = []
        dist.all_gather(objs, obj, group=group)
    else:
        objs = [None for _ in range(dist.get_world_size())]
        # ?????? unpickle ???????????????????????? gpu ??????
        obj = paddle_move_data_to_device(obj, "cpu")
        objs = all_gather_object(objs, obj, group=group)

    return objs


def fastnlp_paddle_broadcast_object(obj, src, device=None, group=None):
    """
    ??? src ?????? obj ????????????????????? rank ??????

    :param obj: ?????????????????????
    :param src: ??????????????????
    :param device:
    :param group: ?????????????????? group
    :return:
    """
    if int(os.environ.get(FASTNLP_NO_SYNC, '0')) == 2:
        if src == dist.get_rank():
            return obj
        else:
            return None

    cur_rank = dist.get_rank()
    if cur_rank == src:
        # ????????? tensor ??????????????? cpu ???????????? pickle , ?????? unpickle ?????????????????? pickle ???????????????????????????
        obj = paddle_move_data_to_device(obj, "cpu")

    if device is None:
        device = paddle.device.get_device()

    if cur_rank == src:
        tensor, size = _object_to_tensor(obj, device=device)
    else:
        size = paddle_move_data_to_device(paddle.to_tensor([0]), device)

    dist.broadcast(size, src=src, group=group)
    if cur_rank != src:
        tensor = paddle.empty(
            size.astype(paddle.int32),  # type: ignore[arg-type]
            dtype=paddle.int32,
        )
    dist.broadcast(tensor, src=src, group=group)

    return _tensor_to_object(tensor, tensor_size=size.item())

def all_gather_object(object_list, obj, group=None):
    """

    Example::
        >>> # Note: Process group initialization omitted on each rank.
        >>> # Assumes world_size of 3.
        >>> gather_objects = ["foo", 12, {1: 2}] # any picklable object
        >>> output = [None for _ in gather_objects]
        >>> all_gather_object(output, gather_objects[dist.get_rank()])
        >>> output
        ['foo', 12, {1: 2}]

    :param object_list:
    :param obj:
    :param group:
    :return:
    """
    if int(os.environ.get(FASTNLP_NO_SYNC, '0')) == 2:
        return [obj]

    if group is not None and not group.is_member():
        return
    
    current_device = paddle.device.get_device()

    input_tensor, local_size = _object_to_tensor(obj, device=current_device)

    # ?????? tensor ??? size??????????????????
    object_size_list = []
    # Allgather tensor sizes
    dist.all_gather(object_size_list, local_size, group=group)
    max_object_size = int(max(object_size_list).item())  # type: ignore[type-var]
    # ??????????????? pad
    pad_dims = []
    pad_by = (max_object_size - local_size).detach().cpu()
    for val in reversed(pad_by):
        pad_dims.append(0)
        pad_dims.append(val.item())
    tensor_padded = paddle.nn.functional.pad(input_tensor, pad_dims)

    # Output tensors are nonoverlapping views of coalesced_output_tensor
    output_tensors = []
    dist.all_gather(output_tensors, tensor_padded, group=group)
    dist.barrier()
    # Deserialize outputs back to object.
    for i, tensor in enumerate(output_tensors):
        tensor = tensor.astype(paddle.uint8)
        if not tensor.place.is_cpu_place():
            tensor = tensor.cpu()
        tensor_size = object_size_list[i]
        object_list[i] = _tensor_to_object(tensor, tensor_size)
    return object_list