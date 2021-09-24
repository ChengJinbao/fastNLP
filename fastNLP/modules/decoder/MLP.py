import torch
import torch.nn as nn

from fastNLP.modules.utils import initial_parameter


class MLP(nn.Module):
    """Multilayer Perceptrons as a decoder

    :param list size_layer: list of int, define the size of MLP layers. layer的层数为 len(size_layer) - 1
    :param str or list activation: str or function or a list, the activation function for hidden layers.
    :param str or function output_activation : str or function, the activation function for output layer
    :param str initial_method: the name of initialization method.
    :param float dropout: the probability of dropout.

    .. note::
        隐藏层的激活函数通过activation定义。一个str/function或者一个str/function的list可以被传入activation。
        如果只传入了一个str/function，那么所有隐藏层的激活函数都由这个str/function定义；
        如果传入了一个str/function的list，那么每一个隐藏层的激活函数由这个list中对应的元素定义，其中list的长度为隐藏层数。
        输出层的激活函数由output_activation定义，默认值为None，此时输出层没有激活函数。
    """

    def __init__(self, size_layer, activation='relu', output_activation=None, initial_method=None, dropout=0.0):
        super(MLP, self).__init__()
        self.hiddens = nn.ModuleList()
        self.output = None
        self.output_activation = output_activation
        for i in range(1, len(size_layer)):
            if i + 1 == len(size_layer):
                self.output = nn.Linear(size_layer[i-1], size_layer[i])
            else:
                self.hiddens.append(nn.Linear(size_layer[i-1], size_layer[i]))

        self.dropout = nn.Dropout(p=dropout)

        actives = {
            'relu': nn.ReLU(),
            'tanh': nn.Tanh(),
            'sigmoid': nn.Sigmoid(),
        }
        if not isinstance(activation, list):
            activation = [activation] * (len(size_layer) - 2)
        elif len(activation) == len(size_layer) - 2:
            pass
        else:
            raise ValueError(
                f"the length of activation function list except {len(size_layer) - 2} but got {len(activation)}!")
        self.hidden_active = []
        for func in activation:
            if callable(activation):
                self.hidden_active.append(activation)
            elif func.lower() in actives:
                self.hidden_active.append(actives[func])
            else:
                raise ValueError("should set activation correctly: {}".format(activation))
        if self.output_activation is not None:
            if callable(self.output_activation):
                pass
            elif self.output_activation.lower() in actives:
                self.output_activation = actives[self.output_activation]
            else:
                raise ValueError("should set activation correctly: {}".format(activation))
        initial_parameter(self, initial_method)

    def forward(self, x):
        for layer, func in zip(self.hiddens, self.hidden_active):
            x = self.dropout(func(layer(x)))
        x = self.output(x)
        if self.output_activation is not None:
            x = self.output_activation(x)
        x = self.dropout(x)
        return x


if __name__ == '__main__':
    net1 = MLP([5, 10, 5])
    net2 = MLP([5, 10, 5], 'tanh')
    net3 = MLP([5, 6, 7, 8, 5], 'tanh')
    net4 = MLP([5, 6, 7, 8, 5], 'relu', output_activation='tanh')
    net5 = MLP([5, 6, 7, 8, 5], ['tanh', 'relu', 'tanh'], 'tanh')
    for net in [net1, net2, net3, net4, net5]:
        x = torch.randn(5, 5)
        y = net(x)
        print(x)
        print(y)
