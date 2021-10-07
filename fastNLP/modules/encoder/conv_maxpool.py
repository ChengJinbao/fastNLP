# python: 3.6
# encoding: utf-8

import torch
import torch.nn as nn
import torch.nn.functional as F

from ..utils import initial_parameter


class ConvMaxpool(nn.Module):
    """集合了Convolution和Max-Pooling于一体的层。
    给定一个batch_size x max_len x input_size的输入，返回batch_size x sum(output_channels) 大小的matrix。在内部，是先使用
    CNN给输入做卷积，然后经过activation激活层，在通过在长度(max_len)这一维进行max_pooling。最后得到每个sample的一个vector
    表示。

    :param int in_channels: 输入channel的大小，一般是embedding的维度; 或encoder的output维度
    :param int,tuple(int) out_channels: 输出channel的数量。如果为list，则需要与kernel_sizes的数量保持一致
    :param int,tuple(int) kernel_sizes: 输出channel的kernel大小。
    :param int stride: 见pytorch Conv1D文档。所有kernel共享一个stride。
    :param int padding: 见pytorch Conv1D文档。所有kernel共享一个padding。
    :param int dilation: 见pytorch Conv1D文档。所有kernel共享一个dilation。
    :param int groups: 见pytorch Conv1D文档。所有kernel共享一个groups。
    :param bool bias: 见pytorch Conv1D文档。所有kernel共享一个bias。
    :param str activation: Convolution后的结果将通过该activation后再经过max-pooling。支持relu, sigmoid, tanh
    :param str initial_method: str。
    """
    def __init__(self, in_channels, out_channels, kernel_sizes,
                 stride=1, padding=0, dilation=1,
                 groups=1, bias=True, activation="relu", initial_method=None):
        super(ConvMaxpool, self).__init__()

        # convolution
        if isinstance(kernel_sizes, (list, tuple, int)):
            if isinstance(kernel_sizes, int) and isinstance(out_channels, int):
                out_channels = [out_channels]
                kernel_sizes = [kernel_sizes]
            elif isinstance(kernel_sizes, (tuple, list)) and isinstance(out_channels, (tuple, list)):
                assert len(out_channels)==len(kernel_sizes), "The number of out_channels should be equal to the number" \
                                                             " of kernel_sizes."
            else:
                raise ValueError("The type of out_channels and kernel_sizes should be the same.")

            self.convs = nn.ModuleList([nn.Conv1d(
                in_channels=in_channels,
                out_channels=oc,
                kernel_size=ks,
                stride=stride,
                padding=padding,
                dilation=dilation,
                groups=groups,
                bias=bias)
                for oc, ks in zip(out_channels, kernel_sizes)])

        else:
            raise Exception(
                'Incorrect kernel sizes: should be list, tuple or int')

        # activation function
        if activation == 'relu':
            self.activation = F.relu
        elif activation == 'sigmoid':
            self.activation = F.sigmoid
        elif activation == 'tanh':
            self.activation = F.tanh
        else:
            raise Exception(
                "Undefined activation function: choose from: relu, tanh, sigmoid")

        initial_parameter(self, initial_method)

    def forward(self, x, mask=None):
        """

        :param torch.FloatTensor x: batch_size x max_len x input_size, 一般是经过embedding后的值
        :param mask: batch_size x max_len, pad的地方为0。不影响卷积运算，max-pool一定不会pool到pad为0的位置
        :return:
        """
        # [N,L,C] -> [N,C,L]
        x = torch.transpose(x, 1, 2)
        # convolution
        xs = [self.activation(conv(x)) for conv in self.convs]  # [[N,C,L], ...]
        if mask is not None:
            mask = mask.unsqueeze(1) # B x 1 x L
            xs = [x.masked_fill_(mask, float('-inf')) for x in xs]
        # max-pooling
        xs = [F.max_pool1d(input=i, kernel_size=i.size(2)).squeeze(2)
              for i in xs]  # [[N, C], ...]
        return torch.cat(xs, dim=-1)  # [N, C]