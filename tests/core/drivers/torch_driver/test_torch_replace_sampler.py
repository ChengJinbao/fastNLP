
import pytest


from fastNLP.envs.imports import _NEED_IMPORT_TORCH

if _NEED_IMPORT_TORCH:
    import torch
    from torch.utils.data import DataLoader


# 框架无关的一些接口测试

"""
模拟
同一个dl，同时传入trainer和evaluator，
    （1）在训练到一半进行evaluate，需要保证trainer中dl的sampler状态不受影响
    （2）evaluate设置新的set_distributed不改变原有trainer中的evaluate
"""

class SequenceDataSet:
    def __init__(self, num_samples):
        self.data = list(range(num_samples))

    def __getitem__(self, item):
        return self.data[item]

    def __len__(self):
        return len(self.data)


def check_replace_sampler(driver):
    # dist_sampler 可以选择的有['dist', 'unrepeatdist', None]或者是ReproducibleSampler，ReproduceBatchSampler
    # reproducible 是 True 和 False

    # 需要 check 返回的 sampler 和 dataloader 都不同了
    assert driver.is_distributed() is False, "This test only for non distributed sampler."
    ds = SequenceDataSet(10)
    dataloader = DataLoader(dataset=ds, batch_size=2, collate_fn=lambda x:x, shuffle=True)

    dl1 = driver.set_dist_repro_dataloader(dataloader, dist='dist', reproducible=True)

    assert not (dl1.sampler is dataloader.sampler), "The sampler should not the same one."
    assert not (dl1 is dataloader), "The dataloader should not the same one."

    # 迭代两个 batch
    already_seen_idx = set()
    for idx, batch in enumerate(dl1):
        already_seen_idx.update(batch)
        if idx > 1:
            sampler_states = dataloader.sampler.state_dict()
            break

    # 再对原来的dataloader进行迭代，应该不影响 dl1 ，即 dl1 应该继续输出剩下的，而不会重复
    for idx, batch in enumerate(dataloader):
        pass

    left_idxes = set()
    for idx, batch in enumerate(dl1):
        for b in batch:
            assert b not in already_seen_idx
        left_idxes.update(batch)

    if not driver.is_distributed():
        # 如果不是分布式的话，应该是等于整个数据的
        assert len(left_idxes)+len(already_seen_idx) == len(ds)

    # 重新加载，应该是可以输出刚才完全一样的
    dl1.sampler.load_state_dict(sampler_states)
    for idx, batch in enumerate(dl1):
        for b in batch:
            assert b not in already_seen_idx
            assert b in left_idxes

    # 需要 check 替换为 unrepeatdist 的时候没有问题:(1) 不会多pad；（2）所有卡互相不重复
    ds = SequenceDataSet(11)
    dataloader = DataLoader(dataset=ds, batch_size=2, collate_fn=lambda x:x, shuffle=True)
    dl1 = driver.set_dist_repro_dataloader(dataloader, dist='unrepeatdist', reproducible=True)
    world_size = 3
    indices = []
    for i in range(world_size):
        dl1.sampler.set_distributed(num_replicas=world_size, rank=i)
        for idx, batch in dl1:
            indices.extend(batch)
    assert len(indices)==len(ds)  # 应该没有任何重复
    assert len(set(indices))==len(indices)  # 应该全是不一样的indice














