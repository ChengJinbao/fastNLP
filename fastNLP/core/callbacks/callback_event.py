from typing import Optional, Callable, Dict
from functools import wraps


__all__ = [
    'Event',
    'Filter'
]


def check_legality(fn):
    @wraps(fn)
    def wrap(every=None, once=None, filter_fn=None):
        if (every is None) and (once is None) and (filter_fn is None):
            every = 1

        if not ((every is not None) ^ (once is not None) ^ (filter_fn is not None)):
            raise ValueError("These three values should be only set one.")

        if (filter_fn is not None) and not callable(filter_fn):
            raise TypeError("Argument filter_fn should be a callable")

        if (every is not None) and not (isinstance(every, int) and every > 0):
            raise ValueError("Argument every should be integer and greater than zero")

        if (once is not None) and not (isinstance(once, int) and once > 0):
            raise ValueError("Argument once should be integer and positive")
        return fn(every=every, once=once, filter_fn=filter_fn)
    return wrap


class Event:
    """
    与 :meth:`Trainer.on` 函数配合使用，达到控制 callback 函数运行时机的目的。

    :param value: Trainer 的 callback 时机；
    :param every: 每触发多少次才真正运行一次；
    :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
    :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
        `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
    """
    every: Optional[int]
    once: Optional[bool]

    def __init__(self, value: str, every: Optional[int] = None, once: Optional[bool] = None,
                 filter_fn: Optional[Callable] = None):
        self.every = every
        self.once = once
        self.filter_fn = filter_fn
        self.value = value

    def __str__(self):
        return "<event={0}, every={1}, once={2}, filter fn is:{3}>".format(self.value, self.every, self.once,
                                                                                self.filter_fn)
    @staticmethod
    def on_after_trainer_initialized(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_after_trainer_initialized` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_after_trainer_initialized', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_sanity_check_begin(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_sanity_check_begin` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        :return:
        """
        return Event(value='on_sanity_check_begin', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_sanity_check_end(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_sanity_check_end` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_sanity_check_end', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_train_begin(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_train_begin` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_train_begin', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_train_end(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_train_end` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_train_end', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_train_epoch_begin(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_train_epoch_begin` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_train_epoch_begin', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_train_epoch_end(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_train_epoch_end` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_train_epoch_end', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_fetch_data_begin(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_fetch_data_begin` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_fetch_data_begin', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_fetch_data_end(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_fetch_data_end` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_fetch_data_end', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_train_batch_begin(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_train_batch_begin` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_train_batch_begin', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_train_batch_end(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_train_batch_end` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_train_batch_end', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_exception(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_exception` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_exception', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_save_model(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_save_model` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_save_model', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_load_model(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_load_model` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_load_model', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_save_checkpoint(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_save_checkpoint` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_save_checkpoint', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_load_checkpoint(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_load_checkpoint` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_load_checkpoint', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_load_checkpoint(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_load_checkpoint` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_load_checkpoint', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_before_backward(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_before_backward` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_before_backward', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_after_backward(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_after_backward` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_after_backward', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_before_optimizers_step(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_before_optimizers_step` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_before_optimizers_step', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_after_optimizers_step(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_after_optimizers_step` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_after_optimizers_step', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_before_zero_grad(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_before_zero_grad` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_before_zero_grad', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_after_zero_grad(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_after_zero_grad` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_after_zero_grad', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_evaluate_begin(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_evaluate_begin` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_evaluate_begin', every=every, once=once, filter_fn=filter_fn)

    @staticmethod
    def on_evaluate_end(every=None, once=None, filter_fn=None):
        """
        当 Trainer 运行到 :func:`on_evaluate_end` 时触发；

        以下三个参数互斥，只能设置其中一个。默认为行为等同于 ``every=1`` 。

        :param every: 每触发多少次才真正运行一次；
        :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
        :param filter_fn: 输入参数的应该为 ``(filter, trainer)``，其中 ``filter`` 对象中包含了 `filter.num_called` 和
            `filter.num_executed` 两个变量分别获取当前被调用了多少次，真正执行了多少次；``trainer`` 对象即为当前正在运行的 Trainer；
        :return:
        """
        return Event(value='on_evaluate_end', every=every, once=once, filter_fn=filter_fn)


class Filter:
    r"""
    可以控制一个函数实际的运行频率的函数修饰器。

    :param every: 表示一个函数隔多少次运行一次；
    :param once: 只在第多少次触发才真正运行一次。即第 ``once`` 次调用时才运行相应的函数，无论之前还是之后均不会运行；
    :param filter_fn: 用户定制的频率控制函数；注意该函数内部的频率判断应当是无状态的，除了参数 `self.num_called` 和
        `self.num_executed` 外，因为我们会在预跑后重置这两个参数的状态；
    """
    def __init__(self, every: Optional[int] = None, once: Optional[int] = None, filter_fn: Optional[Callable] = None):
        # check legality
        check_legality(lambda *args,**kwargs:...)(every, once, filter_fn)
        if (every is None) and (once is None) and (filter_fn is None):
            every = 1
        # 设置变量，包括全局变量；
        self.num_called = 0
        self.num_executed = 0

        if every is not None:
            self._every = every
            self._filter = self.every_filter
        elif once is not None:
            self._once = once
            self._filter = self.once_filter
        else:
            self._filter = filter_fn

    def __call__(self, fn: Callable):

        @wraps(fn)
        def wrapper(*args, **kwargs) -> Callable:
            self.num_called += 1

            # 因为我们的 callback 函数的输入是固定的，而且我们能够保证第一个参数一定是 trainer；
            trainer = args[0]
            if self._filter(self, trainer):
                self.num_executed += 1
                return fn(*args, **kwargs)

        wrapper.__fastNLP_filter__ = self
        return wrapper

    def every_filter(self, *args):
        return self.num_called % self._every == 0

    def once_filter(self, *args):
        return self.num_called == self._once

    def state_dict(self) -> Dict:
        r"""
        通过该函数来保存该 `Filter` 的状态；
        """
        return {"num_called": self.num_called, "num_executed": self.num_executed}

    def load_state_dict(self, state: Dict):
        r"""
        通过该函数来加载 `Filter` 的状态；

        :param state: 通过 `Filter.state_dict` 函数保存的状态元组；
        """
        self.num_called = state["num_called"]
        self.num_executed = state["num_executed"]







