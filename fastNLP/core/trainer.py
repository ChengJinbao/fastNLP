"""
Trainer的说明文档

 .. _Trainer:

Trainer在fastNLP中用于组织单任务的训练过程，可以避免用户在不同训练任务中重复撰写 (1) epoch循环; (2) 将数据分成不同的Batch; (3)
对Batch进行pad; (4) 每个epoch结束或一定step后进行验证集验证; (5) 保存获得更好验证性能的模型等。

1. Trainer的基本使用

    下面的例子是使用神经网络来进行预测一个序列中是否有偶数个1。

    Example::

        import numpy as np
        from torch import nn
        import torch
        import torch.nn.functional as F
        from torch.optim import SGD

        from fastNLP import DataSet
        from fastNLP import Trainer
        from fastNLP.core.losses import CrossEntropyLoss
        from fastNLP.core.metrics import AccuracyMetric
        from fastNLP.modules.decoder import MLP

        # 模型
        class Model(nn.Module):
            def __init__(self, input_num):
                super().__init__()
                self.fcs = MLP([input_num, 40, 40, 2], 'relu')

            def forward(self, x):
                x = self.fcs(x)
                return {'pred': x}
        model = Model(10)

        # 生成数据
        def generate_psedo_dataset(num_samples):
            dataset = DataSet()
            data = np.random.randint(2, size=(num_samples, 10))
            label = np.sum(data, axis=1)%2
            dataset = DataSet({'x':data.astype(float), 'label': label})
            dataset.set_input('x')
            dataset.set_target('label')
            return dataset
        tr_dataset = generate_psedo_dataset(1000)
        dev_data = generate_psedo_dataset(100)

        # 训练
        trainer = Trainer(tr_dataset, model, loss=CrossEntropyLoss(target='label'),
                           optimizer=SGD(model.parameters(), lr=0.1),n_epochs=1000,
                           dev_data = dev_data, metrics=AccuracyMetric(target='label'))
        trainer.train()

    由上面的例子可以看出通过使用Trainer，可以使得训练部分的代码大幅减少。
    使用Trainer需要满足以下几个条件:

    1. 模型

        1. 模型的forward()的参数名需要与DataSet中的名字对应。实际上fastNLP在将DataSet中的数据传递给模型forward()时，是
        通过匹配名称实现的。所以上例中，如果Model的forward函数修改为forward(self, data), 则DataSet中的'x'这个field就应该
        改名为'data'。

        2. 传递给forward()的参数是DataSet中被设置为input的那些field。但如果forward()中没有对应的参数，则不会将数据传递
        给forward()。例如，DataSet中'x1', 'x2'都是input，但是模型的函数为forward(self, x1), 那么'x2'不会传递给forward()。

        3. 模型的forward()返回值需要为一个dict。

    2. Loss

    fastNLP中的为了不限制forward函数的返回内容数量(比如一些复杂任务需要返回多个内容，如Dependency Parsing， Loss_ 与 Metric_ 都使
    用了通过名称来匹配相应内容的策略。如上面的例子中

        Example::

            trainer = Trainer(tr_dataset, model, loss=CrossEntropyLoss(target='label'),
                       optimizer=SGD(model.parameters(), lr=0.1),n_epochs=1000,
                       dev_data = dev_data, metrics=AccuracyMetric(target='label'))

        loss被设置为了 CrossEntropyLoss_ , 但在初始化的时候传入了target='label'这个参数， CrossEntropyLoss_ 的初始化
        参数为(pred=None, target=None, padding_idx=-100)。这里的两个参数分别为计算CrossEntropy时需要使用到的模型的预测值
        与真实值。其中'pred'一般来自于模型forward()的返回结果，'target'一般是来自于DataSet中被设置为target的
        field。由于每个人对真实值或者model的返回值取名并不一样，所以fastNLP的 Loss_ 提供一种类似于映射的机制来匹配
        对应的值，比如这里 CrossEntropyLoss_ 将尝试找到名为'label'的内容来作为真实值得到loss；而pred=None, 则 CrossEntropyLoss_
        使用'pred'作为名称匹配预测值，正好forward的返回值也叫pred，所以这里不需要申明pred。

    尽管fastNLP使用了映射机制来使得loss的计算变得比较灵活，但有些情况下loss必须在模型中进行计算，比如使用了CRF的模型。fastNLP中提供了 LossInForward_ 这
    个loss。这个loss的原理是直接在forward()的返回结果中找到loss_key(默认寻找'loss')指定的那个tensor，
    并使用它作为loss。 如果Trainer初始化没有提供loss则默认使用 LossInForward_ 。详细例子可以参照 TODO 补充一个例子

    3. Metric

    Metric_ 使用了与上述Loss一样的策略，即使用名称进行匹配。AccuracyMetric(target='label')的情况与CrossEntropyLoss 是同理的。

    在进行验证时，可能用到的计算与forward()中不太一致，没有办法直接从forward()的结果中得到预测值，这时模型可以提供一个predict()方法，
    如果提供的模型具有predict方法，则在模型验证时将调用predict()方法获取预测结果，传入到predict()的参数也是从DataSet中被设置为input
    的field中选择出来的; 与forward()一样，返回值需要为一个dict。具体例子可以参考 TODO 补充一个例子

2. Trainer的代码检查

    由于在fastNLP中采取了映射的机制，所以难免可能存在对应出错的情况。Trainer提供一种映射检查机制，可以通过check_code_level来进行控制
    比如下面的例子中，由于各种原因产生的报错

        Example1::

            import numpy as np
            from torch import nn
            import torch
            from torch.optim import SGD
            from fastNLP import Trainer
            from fastNLP import DataSet

            class Model(nn.Module):
                def __init__(self):
                    super().__init__()
                    self.fc = nn.Linear(1, 1)
                def forward(self, x, b):
                    loss = torch.mean((self.fc(x)-b)**2)
                    return {'loss': loss}
            model = Model()

            dataset = DataSet({'a': np.arange(10), 'b':np.arange(10)*2})
            dataset.set_input('a', 'b')

            trainer = Trainer(dataset, model, loss=None, optimizer=SGD(model.parameters(), lr=0.001))

            trainer = Trainer(dataset, model, SGD(model.parameters()))
            #  会报以下的错误
            # input fields after batch(if batch size is 2):
            #     a: (1)type:torch.Tensor (2)dtype:torch.int64, (3)shape:torch.Size([2])
            #     b: (1)type:torch.Tensor (2)dtype:torch.int64, (3)shape:torch.Size([2])
            # There is no target field.
            # ....
            # NameError:
            # Problems occurred when calling Model.forward(self, x, b)
            #     missing param: ['x']
            #     unused field: ['a']
            #     Suggestion: You need to provide ['x'] in DataSet and set it as input.

        这里就是由于在Trainer初始化的时候，fastNLP会尝试使用一个batch_size=2的batch去运行一遍forward()以及backward()。这里有两类
        信息可以为你提供参考

            1. 'input fields after batch...'这部分显示的是train dataset经过Batch操作后，每个field对应的类型以及进行shape。这里
            因为train dataset没有target所以没有显示。根据这里可以看出是否正确将需要的内容设置为了input或target。

            2. NameError，NameError发生在映射出错的情况。这里报错的原因是由于尝试进行forward计算时(可以通过Model.forward(self, x, b)判断
            出当前是在调取forward)，却没有获取到forward()函数中需要的'x'；在报错信息中同时指出了缺'x'，而'a'没有被使用，那么可能
            就是由于field的名称不对。这里将dataset中'a'这个field的名称改为'x'，或者model的参数从'x'修改为'a'都可以解决问题。

        下面的例子是由于loss计算的时候找不到需要的值

        Example2::

            import numpy as np
            from torch import nn
            from torch.optim import SGD
            from fastNLP import Trainer
            from fastNLP import DataSet
            from fastNLP.core.losses import L1Loss
            import torch

            class Model(nn.Module):
                def __init__(self):
                    super().__init__()
                    self.fc = nn.Linear(1, 1)
                def forward(self, a):
                    return {'pred_b': self.fc(a.unsqueeze(1)).squeeze(1), 'No use':1}

            model = Model()

            dataset = DataSet({'a': np.arange(10, dtype=float), 'b':np.arange(10, dtype=float)*2})

            dataset.set_input('a')
            dataset.set_target('b')

            trainer = Trainer(dataset, model, loss=L1Loss(target='label'), optimizer=SGD(model.parameters(), lr=0.001))
            # 报错信息如下
            # input fields after batch(if batch size is 2):
            #     a: (1)type:torch.Tensor (2)dtype:torch.float32, (3)shape:torch.Size([2])
            # target fields after batch(if batch size is 2):
            #     b: (1)type:torch.Tensor (2)dtype:torch.float32, (3)shape:torch.Size([2])
            # ....
            # NameError:
            # Problems occurred when calling L1Loss.get_loss(self, pred, target)
            #     missing param: ['pred(assign to `pred` in `L1Loss`)', 'label(assign to `target` in `L1Loss`)']
            #     unused field: ['b']
            #     unused param: ['pred_b', 'No use']
            #     target field: ['b']
            #     param from Model.forward(self, a): ['pred_b', 'No use']
            #     Suggestion: (1). Check key assignment for `target` when initialize L1Loss. Or provide `label` in DataSet or output of Model.forward(self, a).
            #             (2). Check key assignment for `pred` when initialize L1Loss. Or provide `pred` in DataSet or output of Model.forward(self, a).

        报错信息也包含两部分:

            1. 第一部分与上面是一样的

            2. 这里报错的原因是由于计算loss的时候找不到相应的值(通过L1Loss.get_loss(self, pred, target)判断出来的)；报错的原因是因为
            `pred`和`label`(我们在初始化L1Loss时将target指定为了label)都没有找到。这里'unused field'是DataSet中出现了，但却没有
            被设置为input或者target的field；'unused param'是forward()中返回且没有被使用到的内容；'target field'是被设置为了
            target的field; 'param from Model.forward(self, a)'是forward()返回的所有key。"Suggestion"是关于当前错误处理的建议。

        但是在一些情况下，比如forward()返回值只有一个，target也只有一个，fastNLP不会进行匹配，而直接将forward()的结果作为pred, 将
        DataSet中的target设置为target。上面的例子在返回值中加入了一个'No use'则只是为了使得Loss去匹配结果。


        下面是带有dev dataset时如果出现错误会发生的报错，

        Example3::

            import numpy as np
            from torch import nn
            from torch.optim import SGD
            from fastNLP import Trainer
            from fastNLP import DataSet
            from fastNLP.core.metrics import AccuracyMetric
            import torch

            class Model(nn.Module):
                def __init__(self):
                    super().__init__()
                    self.fc = nn.Linear(1, 1)
                def forward(self, a, b):
                    loss = torch.mean((self.fc(a.float().unsqueeze(1))-b.float())**2)
                    return {'loss': loss}
                def predict(self, a):  # 使用predict()进行验证
                    return {'output':self.fc(a.float().unsqueeze(1))} #这里return的值不包含'pred'这个key
            model = Model()

            dataset = DataSet({'a': np.arange(10), 'b':np.arange(10)*2})
            dev_data = DataSet({'a': np.arange(10, 20), 'b':np.arange(10, 20)*2})

            dataset.set_input('a', 'b')
            dev_data.set_input('a')  # 这里没有设置target

            trainer = Trainer(dataset, model, loss=None, optimizer=SGD(model.parameters(), lr=0.001),
                             dev_data=dev_data, metrics=AccuracyMetric())

            # 报错信息
            # ...
            # NameError:
            # Problems occurred when calling AccuracyMetric.evaluate(self, pred, target, seq_len=None)
            #     missing param: ['pred(assign to `pred` in `AccuracyMetric`)', 'target(assign to `target` in `AccuracyMetric`)']
            #     unused param: ['output']
            #     target field: []
            #     param from Model.predict(self, a): ['output']
            #     Suggestion: (1). Check key assignment for `pred` when initialize AccuracyMetric. Or provide `pred` in DataSet or output of Model.predict(self, a).
            #             (2). Check key assignment for `target` when initialize AccuracyMetric. Or provide `target` in DataSet or output of Model.predict(self, a).

        报错信息和前面都是类似的，但是可以通过'AccuracyMetric.evaluate(self, pred, target, seq_len=None)'看出这里是evaluation
        的时候发生了错误。这样避免了需要在完成一整个epoch的训练才能发现evaluation弄错的情况。这里的修改是通过在初始化metric的时候
        指明通过'output'获取`pred`, 即AccuracyMetric(pred='output')。

    可以通过check_code_level调节检查的强度。默认为0，即进行检查。

3. Trainer与callback

    虽然Trainer本身已经集成了一些功能，但仍然不足以囊括训练过程中可能需要到的功能，比如负采样，learning rate decay, Early Stop等。
    为了解决这个问题fastNLP引入了callback的机制，Callback_ 是一种在Trainer训练过程中特定阶段会运行的函数集合，所有的 Callback_ 都具有
    on_*(比如on_train_start, on_backward_begin)等函数。如果 Callback 实现了该函数，则Trainer运行至对应阶段，会进行调用。

    我们将Train.train()这个函数内部分为以下的阶段，在对应阶段会触发相应的调用。

    Example::

        callback.on_train_begin()  # 开始进行训练
        for i in range(1, n_epochs+1):
            callback.on_epoch_begin()  # 开始新的epoch
            for batch_x, batch_y in Batch:
                callback.on_batch_begin(batch_x, batch_y, indices) # batch_x是设置为input的field，batch_y是设置为target的field
                获取模型输出
                callback.on_loss_begin()
                计算loss
                callback.on_backward_begin() # 可以进行一些检查，比如loss是否为None
                反向梯度回传
                callback.on_backward_end() # 进行梯度截断等
                进行参数更新
                callback.on_step_end()
                callback.on_batch_end()
                # 根据设置进行evaluation，比如这是本epoch最后一个batch或者达到一定step
                if do evaluation:
                    callback.on_valid_begin()
                    进行dev data上的验证
                    callback.on_valid_end()  # 可以进行在其它数据集上进行验证
            callback.on_epoch_end()  # epoch结束调用
        callback.on_train_end() # 训练结束
        callback.on_exception() # 这是一个特殊的步骤，在训练过程中遭遇exception会跳转到这里

    fastNLP已经自带了很多callback函数供使用，可以参考 Callback_ 。一些关于callback的例子，请参考 #TODO callback的例子

"""



import os
import time
from datetime import datetime
from datetime import timedelta

import numpy as np
import torch
from torch import nn
import warnings
try:
    from tqdm.autonotebook import tqdm
except:
    from fastNLP.core.utils import _pseudo_tqdm as tqdm

from fastNLP.core.batch import Batch
from fastNLP.core.callback import CallbackManager, CallbackException
from fastNLP.core.dataset import DataSet
from fastNLP.core.losses import _prepare_losser
from fastNLP.core.metrics import _prepare_metrics
from fastNLP.core.sampler import Sampler
from fastNLP.core.sampler import RandomSampler
from fastNLP.core.sampler import SequentialSampler
from fastNLP.core.tester import Tester
from fastNLP.core.utils import _CheckError
from fastNLP.core.utils import _build_args
from fastNLP.core.utils import _check_forward_error
from fastNLP.core.utils import _check_loss_evaluate
from fastNLP.core.utils import _move_dict_value_to_device
from fastNLP.core.utils import _get_func_signature
from fastNLP.core.utils import _get_device


class Trainer(object):
    def __init__(self, train_data, model, optimizer, loss=None,
                 batch_size=32, sampler=None, update_every=1,
                 n_epochs=10, print_every=5,
                 dev_data=None, metrics=None, metric_key=None,
                 validate_every=-1, save_path=None,
                 prefetch=False, use_tqdm=True, device=None,
                 callbacks=None,
                 check_code_level=0):
        """
        :param DataSet train_data: 训练集
        :param nn.modules model: 待训练的模型
        :param Optimizer,None optimizer: 优化器，pytorch的torch.optim.Optimizer类型。如果为None，则Trainer不会更新模型，
            请确保已在callback中进行了更新。
        :param int batch_size: 训练和验证的时候的batch大小。
        :param LossBase loss: 使用的Loss对象。 详见 LossBase_ 。当loss为None时，默认使用 LossInForward_ 。
        :param Sampler sampler: Batch数据生成的顺序。详见 Sampler_ 。如果为None，默认使用 RandomSampler_ 。
        :param update_every: int, 多少步更新一次梯度。用于希望累计梯度的场景，比如需要128的batch_size, 但是直接设为128
            会导致内存不足，通过设置batch_size=32, update_every=4达到目的。当optimizer为None时，该参数无效。
        :param int n_epochs: 需要优化迭代多少次。
        :param int print_every: 多少次反向传播更新tqdm显示的loss; 如果use_tqdm=False, 则多少次反向传播打印loss。
        :param DataSet dev_data: 用于做验证的DataSet。
        :param MetricBase,list(MetricBase) metrics: 验证的评估函数。可以只使用一个Metric，也可以使用多个Metric，通过
            列表传入。如验证时取得了更好的验证结果(如果有多个Metric，以列表中第一个Metric为准)，且save_path不为None，
            则保存当前模型。Metric种类详见 Metric_ 。仅在传入dev_data时有效。
        :param str,None metric_key:  Metric_ 有时会有多个指标，比如 SpanFPreRecMetric_ 中包含了'f', 'pre', 'rec'。此时需
            要指定以哪个指标为准。另外有些指标是越小效果越好，比如语言模型的困惑度，这种情况下，在key前面增加一个'-'来表
            明验证时，值越小越好(比如: "-ppl")。仅在传入dev_data时有效。
        :param int validate_every: 多少个step在验证集上验证一次; 如果为-1，则每个epoch结束验证一次。仅在传入dev_data时有
            效。
        :param str,None save_path: 将模型保存路径。如果为None，则不保存模型。如果dev_data为None，则保存最后一次迭代的模
            型。保存的时候不仅保存了参数，还保存了模型结构。
        :param prefetch: bool, 是否使用额外的进程对产生batch数据。理论上会使得Batch迭代更快。
        :param bool use_tqdm: 是否使用tqdm来显示训练进度; 如果为False，则将loss打印在终端中。
        :param str,torch.device,None device: 将模型load到哪个设备。默认为None，即Trainer不对模型的计算位置进行管理。支持
            以下的输入str: ['cpu', 'cuda', 'cuda:0', 'cuda:1', ...] 依次为'cpu'中, 可见的第一个GPU中, 可见的第一个GPU中,
            可见的第二个GPU中; torch.device，将模型装载到torch.device上。
        :param list(callbacks) callbacks: 用于在train过程中起调节作用的回调函数。比如early stop，negative sampling等可以
            通过callback机制实现。 可使用的callback参见 Callback_ 。
        :param int check_code_level: 模型检查等级. -1: 不进行检查; 0: 仅出现错误时停止; 1: 如果有field没有被使用，
            报告警告信息; 2: 有任何field没有被使用都报错. 检查的原理是通过使用很小的batch(默认2个sample)来运行代码，但是
            这个过程理论上不会修改任何参数，只是会检查能否运行。但如果(1)模型中存在将batch_size写为某个固定值的情况；
            (2)模型中存在累加前向计算次数的，可能会多计算1次。以上情况建议将check_code_level设置为-1。
        """
        super(Trainer, self).__init__()

        if not isinstance(train_data, DataSet):
            raise TypeError(f"The type of train_data must be fastNLP.DataSet, got {type(train_data)}.")
        if not isinstance(model, nn.Module):
            raise TypeError(f"The type of model must be torch.nn.Module, got {type(model)}.")

        # check metrics and dev_data
        if (not metrics) and dev_data is not None:
            raise ValueError("No metric for dev_data evaluation.")
        if metrics and (dev_data is None):
            raise ValueError("No dev_data for evaluations, pass dev_data or set metrics to None. ")

        # check update every
        assert update_every >= 1, "update_every must be no less than 1."
        self.update_every = int(update_every)

        # check save_path
        if not (save_path is None or isinstance(save_path, str)):
            raise ValueError("save_path can only be None or `str`.")
        # prepare evaluate
        metrics = _prepare_metrics(metrics)

        # parse metric_key
        # increase_better is True. It means the exp result gets better if the indicator increases.
        # It is true by default.
        self.increase_better = True
        if metric_key is not None:
            self.increase_better = False if metric_key[0] == "-" else True
            self.metric_key = metric_key[1:] if metric_key[0] == "+" or metric_key[0] == "-" else metric_key
        elif len(metrics) > 0:
            self.metric_key = metrics[0].__class__.__name__.lower().strip('metric')

        # prepare loss
        losser = _prepare_losser(loss)

        # sampler check
        if sampler is not None and not isinstance(sampler, Sampler):
            raise ValueError("The type of sampler should be fastNLP.BaseSampler, got {}.".format(type(sampler)))

        if check_code_level > -1:
            _check_code(dataset=train_data, model=model, losser=losser, metrics=metrics, dev_data=dev_data,
                        metric_key=metric_key, check_level=check_code_level,
                        batch_size=min(batch_size, DEFAULT_CHECK_BATCH_SIZE))

        self.train_data = train_data
        self.dev_data = dev_data  # If None, No validation.
        self.model = model
        self.losser = losser
        self.metrics = metrics
        self.n_epochs = int(n_epochs)
        self.batch_size = int(batch_size)
        self.save_path = save_path
        self.print_every = int(print_every)
        self.validate_every = int(validate_every) if validate_every != 0 else -1
        self.best_metric_indicator = None
        self.best_dev_epoch = None
        self.best_dev_step = None
        self.best_dev_perf = None
        self.sampler = sampler if sampler is not None else RandomSampler()
        self.prefetch = prefetch
        self.callback_manager = CallbackManager(env={"trainer": self}, callbacks=callbacks)
        self.n_steps = (len(self.train_data) // self.batch_size + int(
            len(self.train_data) % self.batch_size != 0)) * self.n_epochs

        check_exist = check_code_level>-1
        self.device = _get_device(device, check_exist=check_exist)

        if isinstance(optimizer, torch.optim.Optimizer):
            self.optimizer = optimizer
        elif optimizer is None:
            warnings.warn("The optimizer is set to None, Trainer will update your model. Make sure you update the model"
                          " in the callback.")
            self.optimizer = None
        else:
            raise TypeError("optimizer can only be torch.optim.Optimizer type, not {}.".format(type(optimizer)))

        self.use_tqdm = use_tqdm
        self.pbar = None
        self.print_every = abs(self.print_every)

        if self.dev_data is not None:
            self.tester = Tester(model=self.model,
                                 data=self.dev_data,
                                 metrics=self.metrics,
                                 batch_size=self.batch_size,
                                 device=self.device,
                                 verbose=0)

        self.step = 0
        self.start_time = None  # start timestamp

        self.callback_manager = CallbackManager(env={"trainer": self},
                                                callbacks=callbacks)

    def train(self, load_best_model=True):
        """
        使用该函数使Trainer开始训练。

        :param bool load_best_model: 该参数只有在初始化提供了dev_data的情况下有效，如果True, trainer将在返回之前重新加载dev表现
                最好的模型参数。
        :return dict: 返回一个字典类型的数据,
                内含以下内容::

                    seconds: float, 表示训练时长
                    以下三个内容只有在提供了dev_data的情况下会有。
                    best_eval: Dict of Dict, 表示evaluation的结果。第一层的key为Metric的名称，第二层的key为具体的Metric
                    best_epoch: int，在第几个epoch取得的最佳值
                    best_step: int, 在第几个step(batch)更新取得的最佳值

        """
        results = {}
        if self.n_epochs <= 0:
            print(f"training epoch is {self.n_epochs}, nothing was done.")
            results['seconds'] = 0.
            return results
        try:
            if self.device is not None:
                self.model = self.model.to(self.device)
            self._model_device = self.model.parameters().__next__().device
            self._mode(self.model, is_test=False)

            self.start_time = str(datetime.now().strftime('%Y-%m-%d-%H-%M-%S'))
            start_time = time.time()
            print("training epochs started " + self.start_time, flush=True)

            try:
                self.callback_manager.on_train_begin()
                self._train()
                self.callback_manager.on_train_end()
            except (CallbackException, KeyboardInterrupt) as e:
                self.callback_manager.on_exception(e)

            if self.dev_data is not None and hasattr(self, 'best_dev_perf'):
                print(
                    "\nIn Epoch:{}/Step:{}, got best dev performance:".format(self.best_dev_epoch, self.best_dev_step) +
                    self.tester._format_eval_results(self.best_dev_perf), )
                results['best_eval'] = self.best_dev_perf
                results['best_epoch'] = self.best_dev_epoch
                results['best_step'] = self.best_dev_step
                if load_best_model:
                    model_name = "best_" + "_".join([self.model.__class__.__name__, self.metric_key, self.start_time])
                    load_succeed = self._load_model(self.model, model_name)
                    if load_succeed:
                        print("Reloaded the best model.")
                    else:
                        print("Fail to reload best model.")
        finally:
            pass
        results['seconds'] = round(time.time() - start_time, 2)

        return results

    def _train(self):
        if not self.use_tqdm:
            from fastNLP.core.utils import _pseudo_tqdm as inner_tqdm
        else:
            inner_tqdm = tqdm
        self.step = 0
        self.epoch = 0
        start = time.time()

        with inner_tqdm(total=self.n_steps, postfix='loss:{0:<6.5f}', leave=False, dynamic_ncols=True) as pbar:
            self.pbar = pbar if isinstance(pbar, tqdm) else None
            avg_loss = 0
            data_iterator = Batch(self.train_data, batch_size=self.batch_size, sampler=self.sampler, as_numpy=False,
                                  prefetch=self.prefetch)
            self.batch_per_epoch = data_iterator.num_batches
            for epoch in range(1, self.n_epochs + 1):
                self.epoch = epoch
                pbar.set_description_str(desc="Epoch {}/{}".format(epoch, self.n_epochs))
                # early stopping
                self.callback_manager.on_epoch_begin()
                for batch_x, batch_y in data_iterator:
                    self.step += 1
                    _move_dict_value_to_device(batch_x, batch_y, device=self._model_device)
                    indices = data_iterator.get_batch_indices()
                    # negative sampling; replace unknown; re-weight batch_y
                    self.callback_manager.on_batch_begin(batch_x, batch_y, indices)
                    prediction = self._data_forward(self.model, batch_x)

                    # edit prediction
                    self.callback_manager.on_loss_begin(batch_y, prediction)
                    loss = self._compute_loss(prediction, batch_y).mean()
                    avg_loss += loss.item()
                    loss = loss / self.update_every

                    # Is loss NaN or inf? requires_grad = False
                    self.callback_manager.on_backward_begin(loss)
                    self._grad_backward(loss)
                    self.callback_manager.on_backward_end()

                    self._update()
                    self.callback_manager.on_step_end()

                    if self.step % self.print_every == 0:
                        avg_loss = float(avg_loss) / self.print_every
                        if self.use_tqdm:
                            print_output = "loss:{0:<6.5f}".format(avg_loss)
                            pbar.update(self.print_every)
                        else:
                            end = time.time()
                            diff = timedelta(seconds=round(end - start))
                            print_output = "[epoch: {:>3} step: {:>4}] train loss: {:>4.6} time: {}".format(
                                epoch, self.step, avg_loss, diff)
                        pbar.set_postfix_str(print_output)
                        avg_loss = 0
                    self.callback_manager.on_batch_end()

                    if ((self.validate_every > 0 and self.step % self.validate_every == 0) or
                        (self.validate_every < 0 and self.step % len(data_iterator) == 0)) \
                            and self.dev_data is not None:
                        eval_res = self._do_validation(epoch=epoch, step=self.step)
                        eval_str = "Evaluation at Epoch {}/{}. Step:{}/{}. ".format(epoch, self.n_epochs, self.step,
                                                                                    self.n_steps) + \
                                   self.tester._format_eval_results(eval_res)
                        pbar.write(eval_str + '\n')

                # ================= mini-batch end ==================== #

                # lr decay; early stopping
                self.callback_manager.on_epoch_end()
            # =============== epochs end =================== #
            pbar.close()
            self.pbar = None
        # ============ tqdm end ============== #

    def _do_validation(self, epoch, step):
        self.callback_manager.on_valid_begin()
        res = self.tester.test()

        is_better_eval = False
        if self._better_eval_result(res):
            if self.save_path is not None:
                self._save_model(self.model,
                                 "best_" + "_".join([self.model.__class__.__name__, self.metric_key, self.start_time]))
            else:
                self._best_model_states = {name: param.cpu().clone() for name, param in self.model.named_parameters()}
            self.best_dev_perf = res
            self.best_dev_epoch = epoch
            self.best_dev_step = step
            is_better_eval = True
        # get validation results; adjust optimizer
        self.callback_manager.on_valid_end(res, self.metric_key, self.optimizer, is_better_eval)
        return res

    def _mode(self, model, is_test=False):
        """Train mode or Test mode. This is for PyTorch currently.

        :param model: a PyTorch model
        :param bool is_test: whether in test mode or not.

        """
        if is_test:
            model.eval()
        else:
            model.train()

    def _update(self):
        """Perform weight update on a model.

        """
        if self.optimizer is not None and (self.step + 1) % self.update_every == 0:
            self.optimizer.step()

    def _data_forward(self, network, x):
        x = _build_args(network.forward, **x)
        y = network(**x)
        if not isinstance(y, dict):
            raise TypeError(f"The return value of {_get_func_signature(network.forward)} should be dict, got {type(y)}.")
        return y

    def _grad_backward(self, loss):
        """Compute gradient with link rules.

        :param loss: a scalar where back-prop starts

        For PyTorch, just do "loss.backward()"
        """
        if self.step % self.update_every == 0:
            self.model.zero_grad()
        loss.backward()

    def _compute_loss(self, predict, truth):
        """Compute loss given prediction and ground truth.

        :param predict: prediction dict, produced by model.forward
        :param truth: ground truth dict, produced by batch_y
        :return: a scalar
        """
        return self.losser(predict, truth)

    def _save_model(self, model, model_name, only_param=False):
        """ 存储不含有显卡信息的state_dict或model
        :param model:
        :param model_name:
        :param only_param:
        :return:
        """
        if self.save_path is not None:
            model_path = os.path.join(self.save_path, model_name)
            if not os.path.exists(self.save_path):
                os.makedirs(self.save_path, exist_ok=True)
            if only_param:
                state_dict = model.state_dict()
                for key in state_dict:
                    state_dict[key] = state_dict[key].cpu()
                torch.save(state_dict, model_path)
            else:
                model.cpu()
                torch.save(model, model_path)
                model.to(self._model_device)

    def _load_model(self, model, model_name, only_param=False):
        # 返回bool值指示是否成功reload模型
        if self.save_path is not None:
            model_path = os.path.join(self.save_path, model_name)
            if only_param:
                states = torch.load(model_path)
            else:
                states = torch.load(model_path).state_dict()
            model.load_state_dict(states)
        elif hasattr(self, "_best_model_states"):
            model.load_state_dict(self._best_model_states)
        else:
            return False
        return True

    def _better_eval_result(self, metrics):
        """Check if the current epoch yields better validation results.

        :return bool value: True means current results on dev set is the best.
        """
        indicator_val = _check_eval_results(metrics, self.metric_key, self.metrics)
        is_better = True
        if self.best_metric_indicator is None:
            # first-time validation
            self.best_metric_indicator = indicator_val
        else:
            if self.increase_better is True:
                if indicator_val > self.best_metric_indicator:
                    self.best_metric_indicator = indicator_val
                else:
                    is_better = False
            else:
                if indicator_val < self.best_metric_indicator:
                    self.best_metric_indicator = indicator_val
                else:
                    is_better = False
        return is_better


DEFAULT_CHECK_BATCH_SIZE = 2
DEFAULT_CHECK_NUM_BATCH = 2


def _get_value_info(_dict):
    # given a dict value, return information about this dict's value. Return list of str
    strs = []
    for key, value in _dict.items():
        _str = ''
        if isinstance(value, torch.Tensor):
            _str += "\t{}: (1)type:torch.Tensor (2)dtype:{}, (3)shape:{} ".format(key,
                                                                                  value.dtype, value.size())
        elif isinstance(value, np.ndarray):
            _str += "\t{}: (1)type:numpy.ndarray (2)dtype:{}, (3)shape:{} ".format(key,
                                                                                   value.dtype, value.shape)
        else:
            _str += "\t{}: type:{}".format(key, type(value))
        strs.append(_str)
    return strs


def _check_code(dataset, model, losser, metrics, batch_size=DEFAULT_CHECK_BATCH_SIZE,
                dev_data=None, metric_key=None,
                check_level=0):
    # check get_loss 方法
    model_devcie = model.parameters().__next__().device

    batch = Batch(dataset=dataset, batch_size=batch_size, sampler=SequentialSampler())
    for batch_count, (batch_x, batch_y) in enumerate(batch):
        _move_dict_value_to_device(batch_x, batch_y, device=model_devcie)
        # forward check
        if batch_count == 0:
            info_str = ""
            input_fields = _get_value_info(batch_x)
            target_fields = _get_value_info(batch_y)
            if len(input_fields) > 0:
                info_str += "input fields after batch(if batch size is {}):\n".format(batch_size)
                info_str += "\n".join(input_fields)
                info_str += '\n'
            else:
                raise RuntimeError("There is no input field.")
            if len(target_fields) > 0:
                info_str += "target fields after batch(if batch size is {}):\n".format(batch_size)
                info_str += "\n".join(target_fields)
                info_str += '\n'
            else:
                info_str += 'There is no target field.'
            print(info_str)
            _check_forward_error(forward_func=model.forward, dataset=dataset,
                                 batch_x=batch_x, check_level=check_level)

        refined_batch_x = _build_args(model.forward, **batch_x)
        pred_dict = model(**refined_batch_x)
        func_signature = _get_func_signature(model.forward)
        if not isinstance(pred_dict, dict):
            raise TypeError(f"The return value of {func_signature} should be `dict`, not `{type(pred_dict)}`.")

        # loss check
        try:
            loss = losser(pred_dict, batch_y)
            # check loss output
            if batch_count == 0:
                if not isinstance(loss, torch.Tensor):
                    raise TypeError(
                        f"The return value of {_get_func_signature(losser.get_loss)} should be `torch.Tensor`, "
                        f"but got `{type(loss)}`.")
                if len(loss.size()) != 0:
                    raise ValueError(
                        f"The size of return value of {_get_func_signature(losser.get_loss)} is {loss.size()}, "
                        f"should be torch.size([])")
            loss.backward()
        except _CheckError as e:
            # TODO: another error raised if _CheckError caught
            pre_func_signature = _get_func_signature(model.forward)
            _check_loss_evaluate(prev_func_signature=pre_func_signature, func_signature=e.func_signature,
                                 check_res=e.check_res, pred_dict=pred_dict, target_dict=batch_y,
                                 dataset=dataset, check_level=check_level)
        model.zero_grad()
        if batch_count + 1 >= DEFAULT_CHECK_NUM_BATCH:
            break

    if dev_data is not None:
        tester = Tester(data=dev_data[:batch_size * DEFAULT_CHECK_NUM_BATCH], model=model, metrics=metrics,
                        batch_size=batch_size, verbose=-1)
        evaluate_results = tester.test()
        _check_eval_results(metrics=evaluate_results, metric_key=metric_key, metric_list=metrics)


def _check_eval_results(metrics, metric_key, metric_list):
    # metrics: tester返回的结果
    # metric_key: 一个用来做筛选的指标，来自Trainer的初始化
    # metric_list: 多个用来做评价的指标，来自Trainer的初始化
    if isinstance(metrics, tuple):
        loss, metrics = metrics

    if isinstance(metrics, dict):
        if len(metrics) == 1:
            # only single metric, just use it
            metric_dict = list(metrics.values())[0]
            metrics_name = list(metrics.keys())[0]
        else:
            metrics_name = metric_list[0].__class__.__name__
            if metrics_name not in metrics:
                raise RuntimeError(f"{metrics_name} is chosen to do validation, but got {metrics}")
            metric_dict = metrics[metrics_name]

        if len(metric_dict) == 1:
            indicator_val, indicator = list(metric_dict.values())[0], list(metric_dict.keys())[0]
        elif len(metric_dict) > 1 and metric_key is None:
            raise RuntimeError(
                f"Got multiple metric keys: {metric_dict}, but metric_key is not set. Which one to use?")
        else:
            # metric_key is set
            if metric_key not in metric_dict:
                raise RuntimeError(f"metric key {metric_key} not found in {metric_dict}")
            indicator_val = metric_dict[metric_key]
    else:
        raise RuntimeError("Invalid metrics type. Expect {}, got {}".format((tuple, dict), type(metrics)))
    return indicator_val
