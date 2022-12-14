import numpy as np
import pytest
from itertools import chain
from copy import deepcopy
from array import array

from tests.helpers.datasets.normal_data import NormalSampler, NormalBatchSampler
from fastNLP.core.samplers import ReproduceBatchSampler, BucketedBatchSampler, RandomBatchSampler


class TestReproducibleBatchSampler:
    def test_1(self):
        sampler = NormalSampler(num_of_data=100)  # 这里是否是 batchsampler 不影响；

        reproduce_batch_sampler = ReproduceBatchSampler(sampler, batch_size=4, drop_last=False)

        forward_steps = 3
        iterator = iter(reproduce_batch_sampler)
        i = 0
        while i < forward_steps:
            next(iterator)
            i += 1

        # 保存状态；
        state = reproduce_batch_sampler.state_dict()

        assert state == {"index_list": array("I", list(range(100))),
                         "num_consumed_samples": forward_steps * 4,
                         "sampler_type": "ReproduceBatchSampler"}

        # 重新生成一个 batchsampler 然后加载状态；
        sampler = NormalSampler(num_of_data=100)  # 这里是否是 batchsampler 不影响；
        reproduce_batch_sampler = ReproduceBatchSampler(sampler, batch_size=4, drop_last=False)
        reproduce_batch_sampler.load_state_dict(state)

        real_res = []
        supposed_res = (list(range(12, 16)), list(range(16, 20)))
        forward_steps = 2
        iter_dataloader = iter(reproduce_batch_sampler)
        for _ in range(forward_steps):
            real_res.append(next(iter_dataloader))

        for i in range(forward_steps):
            assert supposed_res[i] == real_res[i]

        # 改变 batchsize；
        sampler = NormalSampler(num_of_data=100)  # 这里是否是 batchsampler 不影响；
        reproduce_batch_sampler = ReproduceBatchSampler(sampler, batch_size=7, drop_last=False)
        reproduce_batch_sampler.load_state_dict(state)

        real_res = []
        supposed_res = (list(range(12, 19)), list(range(19, 26)))
        forward_steps = 2
        iter_dataloader = iter(reproduce_batch_sampler)
        for _ in range(forward_steps):
            real_res.append(next(iter_dataloader))

        for i in range(forward_steps):
            assert supposed_res[i] == real_res[i]

        # 断点重训的第二轮是否是一个完整的 dataloader；
        # 先把断点重训所在的那一个 epoch 跑完；
        begin_idx = 26
        while True:
            try:
                data = next(iter_dataloader)
                _batch_size = len(data)
                assert data == list(range(begin_idx, begin_idx + _batch_size))
                begin_idx += _batch_size
            except StopIteration:
                break

        # 开始新的一轮；
        begin_idx = 0
        iter_dataloader = iter(reproduce_batch_sampler)
        while True:
            try:
                data = next(iter_dataloader)
                _batch_size = len(data)
                assert data == list(range(begin_idx, begin_idx + _batch_size))
                begin_idx += _batch_size
            except StopIteration:
                break

    def test_2(self):

        # 测试新的一轮的 index list 是重新生成的，而不是沿用上一轮的；
        before_batch_size = 7
        sampler = NormalSampler(num_of_data=100)
        # 开启 shuffle，来检验断点重训后的第二轮的 index list 是不是重新生成的；
        reproduce_batch_sampler = ReproduceBatchSampler(sampler, before_batch_size, drop_last=False)

        # 将一轮的所有数据保存下来，看是否恢复的是正确的；
        all_supposed_data = []
        forward_steps = 3
        iter_dataloader = iter(reproduce_batch_sampler)
        for _ in range(forward_steps):
            all_supposed_data.extend(next(iter_dataloader))

        # 1. 保存状态
        state = reproduce_batch_sampler.state_dict()

        # 2. 断点重训，重新生成一个 dataloader；
        # 不改变 batch_size；
        sampler = NormalSampler(num_of_data=100, shuffle=True)
        reproduce_batch_sampler = ReproduceBatchSampler(sampler, before_batch_size, drop_last=False)
        reproduce_batch_sampler.load_state_dict(state)

        # 先把这一轮的数据过完；
        pre_index_list = reproduce_batch_sampler.state_dict()["index_list"]
        iter_dataloader = iter(reproduce_batch_sampler)
        while True:
            try:
                all_supposed_data.extend(next(iter_dataloader))
            except StopIteration:
                break
        assert all_supposed_data == list(pre_index_list)

        # 重新开启新的一轮；
        for _ in range(3):
            iter_dataloader = iter(reproduce_batch_sampler)
            res = []
            while True:
                try:
                    res.extend(next(iter_dataloader))
                except StopIteration:
                    break
            assert res != all_supposed_data


class DatasetWithVaryLength:
    def __init__(self, num_of_data=100):
        self.data = np.arange(num_of_data)

    def __getitem__(self, item):
        return self.data[item]

    def __len__(self):
        return len(self.data)


class TestBucketedBatchSampler:
    @pytest.mark.parametrize('shuffle', [True, False])
    @pytest.mark.parametrize('drop_last', [True, False])
    @pytest.mark.parametrize('num', [2, 7, 14, 15, 70, 71])
    def test_single_num_batch(self, shuffle, drop_last, num):
        # 数量不够不报错
        for num in [2, 7, 14, 15, 70, 71]:
            dataset = DatasetWithVaryLength(num_of_data=num)
            before_batch_size = 7
            re_batchsampler = BucketedBatchSampler(dataset, length=dataset.data, batch_size=before_batch_size,
                                                   num_batch_per_bucket=10, drop_last=drop_last,
                                                   shuffle=shuffle)
            count = len(list(iter(re_batchsampler)))
            if drop_last:
                assert count==num//before_batch_size, num
            else:
                assert count==(num+before_batch_size-1)//before_batch_size, num

    @pytest.mark.parametrize('shuffle', [True, False])
    @pytest.mark.parametrize('drop_last', [True, False])
    def test_single(self, shuffle, drop_last):

        before_batch_size = 7
        num_batch_per_bucket = 4  # 那么任意 batch 内的长度差值不应该超过4

        dataset = DatasetWithVaryLength(num_of_data=1000)
        re_batchsampler = BucketedBatchSampler(dataset, length=dataset.data, batch_size=before_batch_size,
                                               num_batch_per_bucket=num_batch_per_bucket, drop_last=drop_last,
                                               shuffle=shuffle)
        re_batchsampler.set_epoch(0)
        forward_steps = 10
        iterator = iter(re_batchsampler)
        already_generate_indices = set()
        for _ in range(forward_steps):
            batch = next(iterator)
            assert max(batch) - min(batch) <= before_batch_size * num_batch_per_bucket
            already_generate_indices.update(batch)

        # 1. 保存状态
        state = re_batchsampler.state_dict()

        # 2. 断点重训，继续训练
        re_batchsampler2 = BucketedBatchSampler(dataset, length=dataset.data, batch_size=before_batch_size,
                                               num_batch_per_bucket=num_batch_per_bucket, drop_last=drop_last,
                                               shuffle=shuffle)
        re_batchsampler2.load_state_dict(state)
        re_batchsampler2.set_epoch(0)
        new_already_generate_indices = set()
        mask = np.ones(len(dataset), dtype=bool)
        mask[list(already_generate_indices)] = 0
        indices = np.arange(len(dataset))[mask]
        max_diff = -1
        for i in range(len(indices)-before_batch_size * num_batch_per_bucket):
            max_diff = max(max_diff, indices[i+before_batch_size * num_batch_per_bucket]-indices[i])
        for batch in re_batchsampler2:
            assert max(batch) - min(batch) <= max_diff
            for b in batch:
                assert b not in already_generate_indices
            new_already_generate_indices.update(batch)
        if drop_last is False:
            assert len(new_already_generate_indices.union(already_generate_indices))==len(dataset)

        # 改变 batch_size；
        after_batch_size = 3
        re_batchsampler3 = BucketedBatchSampler(dataset, length=dataset.data, batch_size=after_batch_size,
                                                num_batch_per_bucket=num_batch_per_bucket, drop_last=drop_last,
                                                shuffle=shuffle)
        re_batchsampler3.load_state_dict(state)
        re_batchsampler3.set_epoch(0)
        count = 0

        mask = np.ones(len(dataset), dtype=bool)
        mask[list(already_generate_indices)] = 0
        indices = np.arange(len(dataset))[mask]
        max_diff = -1
        for i in range(len(indices)-after_batch_size * num_batch_per_bucket):
            max_diff = max(max_diff, indices[i+after_batch_size * num_batch_per_bucket]-indices[i])

        for batch in re_batchsampler3:
            assert max(batch) - min(batch) <= max_diff
            for b in batch:
                assert b not in already_generate_indices
            already_generate_indices.update(batch)
            count += 1
            if count > 5:
                break

        # 再 save ，不允许再上个epoch没结束继续sample
        after_batch_size = 5
        with pytest.raises(RuntimeError):
            state = re_batchsampler3.state_dict()

        for batch in re_batchsampler3:  # consume all, 这样才能save
            pass

        already_generate_indices = set()
        count = 0
        for batch in re_batchsampler3:  # 重新开始
            assert max(batch) - min(batch) <= max_diff
            for b in batch:
                assert b not in already_generate_indices
            already_generate_indices.update(batch)
            count += 1
            if count > 5:
                break

        state = re_batchsampler3.state_dict()
        # 这里的 drop_last 为 False，需要最终是所有 sample
        re_batchsampler4 = BucketedBatchSampler(dataset, length=dataset.data, batch_size=after_batch_size,
                                                num_batch_per_bucket=num_batch_per_bucket, drop_last=False,
                                                shuffle=shuffle)
        re_batchsampler4.load_state_dict(state)
        re_batchsampler4.set_epoch(0)

        mask = np.ones(len(dataset), dtype=bool)
        mask[list(already_generate_indices)] = 0
        indices = np.arange(len(dataset))[mask]
        max_diff = -1
        for i in range(len(indices) - after_batch_size * num_batch_per_bucket):
            max_diff = max(max_diff, indices[i + after_batch_size * num_batch_per_bucket] - indices[i])

        for batch in re_batchsampler4:
            assert max(batch) - min(batch) <= max_diff
            for b in batch:
                assert b not in already_generate_indices
            already_generate_indices.update(batch)

        assert len(already_generate_indices) == len(dataset)

    @pytest.mark.parametrize('shuffle', [True, False])
    @pytest.mark.parametrize('drop_last', [True, False])
    @pytest.mark.parametrize('pad', [True, False])
    def test_multi(self, shuffle, drop_last, pad):
    # def test_multi(self, shuffle=True, drop_last=False, pad=False):

        # no shuffle
        num_replica = 2
        dataset = DatasetWithVaryLength(num_of_data=1000)
        batch_size = 5
        num_batch_per_bucket = 10
        lengths = []
        rank0_already_seen_indexes = None
        max_diff = num_batch_per_bucket * batch_size * num_replica
        for rank in range(num_replica):
            sampler = BucketedBatchSampler(dataset, length=dataset.data, batch_size = batch_size,
                                           num_batch_per_bucket = num_batch_per_bucket,
                                           shuffle = shuffle, drop_last=drop_last)
            sampler.set_epoch(0)
            sampler.set_distributed(num_replica, rank=rank, pad=pad)
            lengths.append(len(sampler))
            already_seen_indexes = set()
            repeat_count = 0
            for batch in sampler:
                assert max_diff>=max(batch)-min(batch)
                for b in batch:
                    repeat_count += int(b in already_seen_indexes)
                    if rank0_already_seen_indexes:  # 不能交叉出现
                        assert b not in rank0_already_seen_indexes
                already_seen_indexes.update(batch)
            if rank0_already_seen_indexes is None:
                rank0_already_seen_indexes = already_seen_indexes
            if pad:  # 应该允许重复一次
                assert repeat_count<=1
            else:
                assert repeat_count==0

        assert len(set(lengths))==1, lengths  # 每个进程的batch数量一致

        # 多进程的保存
        already_seen_indexes = set()
        for rank in range(num_replica):
            sampler = BucketedBatchSampler(dataset, length=dataset.data, batch_size = batch_size,
                                           num_batch_per_bucket = num_batch_per_bucket,
                                           shuffle = shuffle, drop_last=drop_last)
            sampler.set_epoch(0)
            sampler.set_distributed(num_replica, rank=rank, pad=pad)
            lengths.append(len(sampler))
            count = 0
            for batch in sampler:
                assert max_diff>=max(batch)-min(batch)
                already_seen_indexes.update(batch)
                if count>5:
                    break
                count += 1
            state = sampler.state_dict()

        # 切换成单机
        new_batch_size = 6
        num_batch_per_bucket = 3
        new_sampler = BucketedBatchSampler(dataset, length=dataset.data, batch_size=new_batch_size,
                                           num_batch_per_bucket=num_batch_per_bucket,
                                           shuffle=shuffle, drop_last=drop_last)
        new_sampler.load_state_dict(state)
        repeat_count = 0
        new_already_seen_indexes = set(list(already_seen_indexes))

        mask = np.ones(len(dataset), dtype=bool)
        mask[list(already_seen_indexes)] = 0
        indices = np.arange(len(dataset))[mask]
        max_diff = -1
        for i in range(len(indices)-new_batch_size * num_batch_per_bucket):
            max_diff = max(max_diff, indices[i+new_batch_size * num_batch_per_bucket]-indices[i])

        for batch in new_sampler:
            assert max_diff>=max(batch)-min(batch)
            for b in batch:
                repeat_count += int(b in new_already_seen_indexes)
            new_already_seen_indexes.update(batch)
        if pad:  # 应该允许重复一次
            assert repeat_count <= 1
        else:
            assert repeat_count == 0
        if drop_last is False:  # 如果没有drop应该相等
            assert len(new_already_seen_indexes)==len(dataset)

        # 测试替换卡的数量。
        num_replica = 3
        new_sampler = BucketedBatchSampler(dataset, length=dataset.data, batch_size=new_batch_size,
                                           num_batch_per_bucket=num_batch_per_bucket,
                                           shuffle=shuffle, drop_last=drop_last)
        new_sampler.set_epoch(0)
        new_sampler.load_state_dict(state)
        new_sampler.set_distributed(num_replicas=num_replica, rank=1, pad=pad)
        repeat_count = 0

        mask = np.ones(len(dataset), dtype=bool)
        mask[list(already_seen_indexes)] = 0
        indices = np.arange(len(dataset))[mask]
        max_diff = -1
        for i in range(len(indices) - new_batch_size * num_batch_per_bucket*num_replica):
            max_diff = max(max_diff, indices[i + new_batch_size * num_batch_per_bucket*num_replica] - indices[i])

        for batch in new_sampler:
            assert max_diff>=max(batch)-min(batch)
            for b in batch:
                repeat_count += int(b in already_seen_indexes)
        if pad:  # 应该允许重复一次
            assert repeat_count <= 1
        else:
            assert repeat_count == 0

    @pytest.mark.parametrize('shuffle', [True, False])
    @pytest.mark.parametrize('drop_last', [True, False])
    @pytest.mark.parametrize('pad', [True, False])
    @pytest.mark.parametrize('num_samples', [13, 100, 623, 1000])
    @pytest.mark.parametrize('num_replicas', [2, 3])
    def test_multi_same_bucket(self, shuffle, drop_last, pad, num_samples, num_replicas):
    # def test_multi_same_bucket(self, shuffle=True, drop_last=True, pad=True, num_samples=623, num_replicas=2):
        dataset = DatasetWithVaryLength(num_of_data=num_samples)
        batch_size = 6
        if num_replicas*batch_size > num_samples:
            return
        num_batch_per_bucket = 10
        samplers = []
        lengths = []
        for i in range(num_replicas):
            sampler = BucketedBatchSampler(dataset, length=dataset.data, batch_size=batch_size,
                                            num_batch_per_bucket=num_batch_per_bucket, shuffle=shuffle, drop_last=drop_last)
            sampler.set_distributed(num_replicas, rank=i, pad=pad)
            sampler.set_epoch(0)
            samplers.append(sampler)
            lengths.append(len(list(iter(sampler))))
        assert len(set(lengths))==1
        bucket_diff = batch_size * num_batch_per_bucket * num_replicas

        for bs in zip(*samplers):
            diff = max(chain(*bs)) - min(chain(*bs))
            assert diff <= bucket_diff

    @pytest.mark.parametrize('shuffle', [True, False])
    @pytest.mark.parametrize('drop_last', [True, False])
    @pytest.mark.parametrize('pad', [True, False])
    @pytest.mark.parametrize('num_samples', [13, 100, 623, 1000])
    @pytest.mark.parametrize('num_replicas', [1, 2, 3])
    def test_multi_save_load(self, shuffle, drop_last, pad, num_samples, num_replicas):
        """
        测试是否能够正确地恢复使用过的（forward）数据

        :return:
        """
        batch_size = 6
        num_batch_per_bucket = 10
        dataset = DatasetWithVaryLength(num_of_data=num_samples)
        samplers = []
        num_consumed_samples_array = list(range(0, num_samples+num_replicas, num_replicas))
        for i in range(num_replicas):
            sampler = BucketedBatchSampler(dataset, length=dataset.data, batch_size=batch_size,
                                           num_batch_per_bucket=num_batch_per_bucket, shuffle=shuffle, drop_last=drop_last)

            sampler.set_distributed(num_replicas=num_replicas, rank=i, pad=pad)
            samplers.append(sampler)
        count = 0
        already_seen_sets = [set()]
        already_seen_set = set()
        for batchs in zip(*samplers):
            batch = chain(*batchs)
            already_seen_set.update(batch)
            already_seen_sets.append(deepcopy(already_seen_set))
            count += 1
            if count > 3:
                break
        states = samplers[0].state_dict()
        for i in range(len(already_seen_sets)):
            states['num_consumed_samples'] = num_consumed_samples_array[i]
            sampler = BucketedBatchSampler(dataset, length=dataset.data, batch_size=batch_size+1,
                                           num_batch_per_bucket=num_batch_per_bucket, shuffle=shuffle,
                                           drop_last=drop_last)
            sampler.set_epoch(0)
            already_seen_set = deepcopy(already_seen_sets[i])
            for batch in sampler:
                already_seen_set.update(batch)
            assert len(already_seen_set) == len(dataset) if drop_last is False else len(already_seen_set) <= len(
                dataset)

        # 测试保存之后再次保存
        sampler = BucketedBatchSampler(dataset, length=dataset.data, batch_size=batch_size + 1,
                                       num_batch_per_bucket=num_batch_per_bucket, shuffle=shuffle,
                                       drop_last=drop_last)
        sampler.set_epoch(0)
        states['num_consumed_samples'] = num_consumed_samples_array[2]
        if len(already_seen_sets)<3:
            return
        already_seen_set = already_seen_sets[2]
        count = 0
        for batch in sampler:
            already_seen_set.update(batch)
            count += 1
            if count > 6:
                break

        states = sampler.state_dict()
        num_consumed_samples_array = list(range(len(dataset)))
        states['num_consumed_samples'] = num_consumed_samples_array[count]
        sampler = BucketedBatchSampler(dataset, length=dataset.data, batch_size=batch_size//2,
                                       num_batch_per_bucket=num_batch_per_bucket, shuffle=shuffle,
                                       drop_last=drop_last)
        sampler.load_state_dict(states)
        sampler.set_epoch(0)
        for batch in sampler:
            already_seen_set.update(batch)

        assert len(already_seen_set)==len(dataset) if drop_last is False else len(already_seen_set)<=len(dataset)


class TestRandomBatchSampler:
    @pytest.mark.parametrize('shuffle', [True, False])
    @pytest.mark.parametrize('drop_last', [True, False])
    @pytest.mark.parametrize('num', [2, 7, 14, 15, 70, 71])
    def test_single_num_batch(self, shuffle, drop_last, num):
        # 数量不够不报错
        for num in [2, 7, 14, 15, 70, 71]:
            dataset = DatasetWithVaryLength(num_of_data=num)
            before_batch_size = 7
            re_batchsampler = RandomBatchSampler(dataset, length=dataset.data, batch_size=before_batch_size,
                                                   drop_last=drop_last,
                                                   shuffle=shuffle)
            count = len(list(iter(re_batchsampler)))
            if drop_last:
                assert count==num//before_batch_size, num
            else:
                assert count==(num+before_batch_size-1)//before_batch_size, num

    @pytest.mark.parametrize('shuffle', [True, False])
    @pytest.mark.parametrize('drop_last', [True, False])
    def test_single(self, shuffle, drop_last):

        before_batch_size = 7
        num_batch_per_bucket = 4  # 那么任意 batch 内的长度差值不应该超过4

        dataset = DatasetWithVaryLength(num_of_data=1000)
        re_batchsampler = RandomBatchSampler(dataset, length=dataset.data, batch_size=before_batch_size,
                                               drop_last=drop_last,
                                               shuffle=shuffle)
        re_batchsampler.set_epoch(0)
        forward_steps = 10
        iterator = iter(re_batchsampler)
        already_generate_indices = set()
        for _ in range(forward_steps):
            batch = next(iterator)
            already_generate_indices.update(batch)

        # 1. 保存状态
        state = re_batchsampler.state_dict()

        # 2. 断点重训，继续训练
        re_batchsampler2 = RandomBatchSampler(dataset, length=dataset.data, batch_size=before_batch_size,
                                                drop_last=drop_last,
                                                shuffle=shuffle)
        re_batchsampler2.load_state_dict(state)
        re_batchsampler2.set_epoch(0)
        new_already_generate_indices = set()
        mask = np.ones(len(dataset), dtype=bool)
        mask[list(already_generate_indices)] = 0
        indices = np.arange(len(dataset))[mask]
        max_diff = -1
        for i in range(len(indices)-before_batch_size * num_batch_per_bucket):
            max_diff = max(max_diff, indices[i+before_batch_size * num_batch_per_bucket]-indices[i])
        for batch in re_batchsampler2:
            for b in batch:
                assert b not in already_generate_indices
            new_already_generate_indices.update(batch)
        if drop_last is False:
            assert len(new_already_generate_indices.union(already_generate_indices))==len(dataset)

        # 改变 batch_size；
        after_batch_size = 3
        re_batchsampler3 = RandomBatchSampler(dataset, length=dataset.data, batch_size=after_batch_size,
                                                drop_last=drop_last,
                                                shuffle=shuffle)
        re_batchsampler3.load_state_dict(state)
        re_batchsampler3.set_epoch(0)
        count = 0

        mask = np.ones(len(dataset), dtype=bool)
        mask[list(already_generate_indices)] = 0
        indices = np.arange(len(dataset))[mask]

        for batch in re_batchsampler3:
            for b in batch:
                assert b not in already_generate_indices
            already_generate_indices.update(batch)
            count += 1
            if count > 5:
                break

        # 再 save ，不允许再上个epoch没结束继续sample
        after_batch_size = 5
        with pytest.raises(RuntimeError):
            state = re_batchsampler3.state_dict()

        for batch in re_batchsampler3:  # consume all, 这样才能save
            pass

        already_generate_indices = set()
        count = 0
        for batch in re_batchsampler3:  # 重新开始
            for b in batch:
                assert b not in already_generate_indices
            already_generate_indices.update(batch)
            count += 1
            if count > 5:
                break

        state = re_batchsampler3.state_dict()
        # 这里的 drop_last 为 False，需要最终是所有 sample
        re_batchsampler4 = RandomBatchSampler(dataset, length=dataset.data, batch_size=after_batch_size,
                                                drop_last=False,
                                                shuffle=shuffle)
        re_batchsampler4.load_state_dict(state)
        re_batchsampler4.set_epoch(0)

        mask = np.ones(len(dataset), dtype=bool)
        mask[list(already_generate_indices)] = 0
        for batch in re_batchsampler4:
            for b in batch:
                assert b not in already_generate_indices
            already_generate_indices.update(batch)

        assert len(already_generate_indices) == len(dataset)

    @pytest.mark.parametrize('shuffle', [True, False])
    @pytest.mark.parametrize('drop_last', [True, False])
    @pytest.mark.parametrize('pad', [True, False])
    def test_multi(self, shuffle, drop_last, pad):
        # def test_multi(self, shuffle=True, drop_last=False, pad=False):

        # no shuffle
        num_replica = 2
        dataset = DatasetWithVaryLength(num_of_data=1000)
        batch_size = 5
        num_batch_per_bucket = 10
        lengths = []
        rank0_already_seen_indexes = None
        max_diff = num_batch_per_bucket * batch_size * num_replica
        for rank in range(num_replica):
            sampler = RandomBatchSampler(dataset, length=dataset.data, batch_size = batch_size,
                                           shuffle = shuffle, drop_last=drop_last)
            sampler.set_epoch(0)
            sampler.set_distributed(num_replica, rank=rank, pad=pad)
            lengths.append(len(sampler))
            already_seen_indexes = set()
            repeat_count = 0
            for batch in sampler:
                for b in batch:
                    repeat_count += int(b in already_seen_indexes)
                    if rank0_already_seen_indexes:  # 不能交叉出现
                        assert b not in rank0_already_seen_indexes
                already_seen_indexes.update(batch)
            if rank0_already_seen_indexes is None:
                rank0_already_seen_indexes = already_seen_indexes
            if pad:  # 应该允许重复一次
                assert repeat_count<=1
            else:
                assert repeat_count==0

        assert len(set(lengths))==1, lengths  # 每个进程的batch数量一致

        # 多进程的保存
        already_seen_indexes = set()
        for rank in range(num_replica):
            sampler = RandomBatchSampler(dataset, length=dataset.data, batch_size = batch_size,
                                           shuffle = shuffle, drop_last=drop_last)
            sampler.set_epoch(0)
            sampler.set_distributed(num_replica, rank=rank, pad=pad)
            lengths.append(len(sampler))
            count = 0
            for batch in sampler:
                already_seen_indexes.update(batch)
                if count>5:
                    break
                count += 1
            state = sampler.state_dict()

        # 切换成单机
        new_batch_size = 6
        num_batch_per_bucket = 3
        new_sampler = RandomBatchSampler(dataset, length=dataset.data, batch_size=new_batch_size,
                                           shuffle=shuffle, drop_last=drop_last)
        new_sampler.load_state_dict(state)
        repeat_count = 0
        new_already_seen_indexes = set(list(already_seen_indexes))

        mask = np.ones(len(dataset), dtype=bool)
        mask[list(already_seen_indexes)] = 0
        indices = np.arange(len(dataset))[mask]

        for batch in new_sampler:
            for b in batch:
                repeat_count += int(b in new_already_seen_indexes)
            new_already_seen_indexes.update(batch)
        if pad:  # 应该允许重复一次
            assert repeat_count <= 1
        else:
            assert repeat_count == 0
        if drop_last is False:  # 如果没有drop应该相等
            assert len(new_already_seen_indexes)==len(dataset)

        # 测试替换卡的数量。
        num_replica = 3
        new_sampler = RandomBatchSampler(dataset, length=dataset.data, batch_size=new_batch_size,
                                           shuffle=shuffle, drop_last=drop_last)
        new_sampler.set_epoch(0)
        new_sampler.load_state_dict(state)
        new_sampler.set_distributed(num_replicas=num_replica, rank=1, pad=pad)
        repeat_count = 0

        mask = np.ones(len(dataset), dtype=bool)
        mask[list(already_seen_indexes)] = 0
        indices = np.arange(len(dataset))[mask]

        for batch in new_sampler:
            for b in batch:
                repeat_count += int(b in already_seen_indexes)
        if pad:  # 应该允许重复一次
            assert repeat_count <= 1
        else:
            assert repeat_count == 0

    @pytest.mark.parametrize('shuffle', [True, False])
    @pytest.mark.parametrize('drop_last', [True, False])
    @pytest.mark.parametrize('pad', [True, False])
    @pytest.mark.parametrize('num_samples', [13, 100, 623, 1000])
    @pytest.mark.parametrize('num_replicas', [2, 3])
    def test_multi_same_bucket(self, shuffle, drop_last, pad, num_samples, num_replicas):
        # def test_multi_same_bucket(self, shuffle=True, drop_last=True, pad=True, num_samples=623, num_replicas=2):
        dataset = DatasetWithVaryLength(num_of_data=num_samples)
        batch_size = 6
        if num_replicas*batch_size > num_samples:
            return
        num_batch_per_bucket = 10
        samplers = []
        lengths = []
        for i in range(num_replicas):
            sampler = RandomBatchSampler(dataset, length=dataset.data, batch_size=batch_size,
                                         shuffle=shuffle, drop_last=drop_last)
            sampler.set_distributed(num_replicas, rank=i, pad=pad)
            sampler.set_epoch(0)
            samplers.append(sampler)
            lengths.append(len(list(iter(sampler))))
        assert len(set(lengths))==1

    @pytest.mark.parametrize('shuffle', [True, False])
    @pytest.mark.parametrize('drop_last', [True, False])
    @pytest.mark.parametrize('pad', [True, False])
    @pytest.mark.parametrize('num_samples', [13, 100, 623, 1000])
    @pytest.mark.parametrize('num_replicas', [1, 2, 3])
    def test_multi_save_load(self, shuffle, drop_last, pad, num_samples, num_replicas):
        """
        测试是否能够正确地恢复使用过的（forward）数据

        :return:
        """
        batch_size = 6
        dataset = DatasetWithVaryLength(num_of_data=num_samples)
        samplers = []
        num_consumed_samples_array = list(range(0, num_samples+num_replicas, num_replicas))
        for i in range(num_replicas):
            sampler = RandomBatchSampler(dataset, length=dataset.data, batch_size=batch_size,
                                           shuffle=shuffle, drop_last=drop_last)

            sampler.set_distributed(num_replicas=num_replicas, rank=i, pad=pad)
            samplers.append(sampler)
        count = 0
        already_seen_sets = [set()]
        already_seen_set = set()
        for batchs in zip(*samplers):
            batch = chain(*batchs)
            already_seen_set.update(batch)
            already_seen_sets.append(deepcopy(already_seen_set))
            count += 1
            if count > 3:
                break
        states = samplers[0].state_dict()
        for i in range(len(already_seen_sets)):
            states['num_consumed_samples'] = num_consumed_samples_array[i]
            sampler = BucketedBatchSampler(dataset, length=dataset.data, batch_size=batch_size+1,
                                           shuffle=shuffle, drop_last=drop_last)
            sampler.set_epoch(0)
            already_seen_set = deepcopy(already_seen_sets[i])
            for batch in sampler:
                already_seen_set.update(batch)
            assert len(already_seen_set) == len(dataset) if drop_last is False else len(already_seen_set) <= len(
                dataset)

        # 测试保存之后再次保存
        sampler = RandomBatchSampler(dataset, length=dataset.data, batch_size=batch_size + 1,
                                       shuffle=shuffle,
                                       drop_last=drop_last)
        sampler.set_epoch(0)
        states['num_consumed_samples'] = num_consumed_samples_array[2]
        if len(already_seen_sets)<3:
            return
        already_seen_set = already_seen_sets[2]
        count = 0
        for batch in sampler:
            already_seen_set.update(batch)
            count += 1
            if count > 6:
                break

        states = sampler.state_dict()
        num_consumed_samples_array = list(range(len(dataset)))
        states['num_consumed_samples'] = num_consumed_samples_array[count]
        sampler = RandomBatchSampler(dataset, length=dataset.data, batch_size=batch_size//2,
                                       shuffle=shuffle,
                                       drop_last=drop_last)
        sampler.load_state_dict(states)
        sampler.set_epoch(0)
        for batch in sampler:
            already_seen_set.update(batch)

        assert len(already_seen_set)==len(dataset) if drop_last is False else len(already_seen_set)<=len(dataset)
