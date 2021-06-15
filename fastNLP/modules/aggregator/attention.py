import math

import torch
import torch.nn.functional as F
from torch import nn

from fastNLP.modules.utils import mask_softmax


class Attention(torch.nn.Module):
    def __init__(self, normalize=False):
        super(Attention, self).__init__()
        self.normalize = normalize

    def forward(self, query, memory, mask):
        similarities = self._atten_forward(query, memory)
        if self.normalize:
            return mask_softmax(similarities, mask)
        return similarities

    def _atten_forward(self, query, memory):
        raise NotImplementedError


class DotAtte(nn.Module):
    def __init__(self, key_size, value_size):
        super(DotAtte, self).__init__()
        self.key_size = key_size
        self.value_size = value_size
        self.scale = math.sqrt(key_size)

    def forward(self, Q, K, V, seq_mask=None):
        """

        :param Q: [batch, seq_len, key_size]
        :param K: [batch, seq_len, key_size]
        :param V: [batch, seq_len, value_size]
        :param seq_mask: [batch, seq_len]
        """
        output = torch.matmul(Q, K.transpose(1, 2)) / self.scale
        if seq_mask is not None:
            output.masked_fill_(seq_mask.lt(1), -float('inf'))
        output = nn.functional.softmax(output, dim=2)
        return torch.matmul(output, V)


class MultiHeadAtte(nn.Module):
    def __init__(self, input_size, output_size, key_size, value_size, num_atte):
        super(MultiHeadAtte, self).__init__()
        self.in_linear = nn.ModuleList()
        for i in range(num_atte * 3):
            out_feat = key_size if (i % 3) != 2 else value_size
            self.in_linear.append(nn.Linear(input_size, out_feat))
        self.attes = nn.ModuleList([DotAtte(key_size, value_size) for _ in range(num_atte)])
        self.out_linear = nn.Linear(value_size * num_atte, output_size)

    def forward(self, Q, K, V, seq_mask=None):
        heads = []
        for i in range(len(self.attes)):
            j = i * 3
            qi, ki, vi = self.in_linear[j](Q), self.in_linear[j+1](K), self.in_linear[j+2](V)
            headi = self.attes[i](qi, ki, vi, seq_mask)
            heads.append(headi)
        output = torch.cat(heads, dim=2)
        return self.out_linear(output)


class Bi_Attention(nn.Module):
    def __init__(self):
        super(Bi_Attention, self).__init__()
        self.inf = 10e12

    def forward(self, in_x1, in_x2, x1_len, x2_len):
        # in_x1: [batch_size, x1_seq_len, hidden_size]
        # in_x2: [batch_size, x2_seq_len, hidden_size]
        # x1_len: [batch_size, x1_seq_len]
        # x2_len: [batch_size, x2_seq_len]

        assert in_x1.size()[0] == in_x2.size()[0]
        assert in_x1.size()[2] == in_x2.size()[2]
        # The batch size and hidden size must be equal.
        assert in_x1.size()[1] == x1_len.size()[1] and in_x2.size()[1] == x2_len.size()[1]
        # The seq len in in_x and x_len must be equal.
        assert in_x1.size()[0] == x1_len.size()[0] and x1_len.size()[0] == x2_len.size()[0]

        batch_size = in_x1.size()[0]
        x1_max_len = in_x1.size()[1]
        x2_max_len = in_x2.size()[1]

        in_x2_t = torch.transpose(in_x2, 1, 2)  # [batch_size, hidden_size, x2_seq_len]

        attention_matrix = torch.bmm(in_x1, in_x2_t)  # [batch_size, x1_seq_len, x2_seq_len]

        a_mask = x1_len.le(0.5).float() * -self.inf  # [batch_size, x1_seq_len]
        a_mask = a_mask.view(batch_size, x1_max_len, -1)
        a_mask = a_mask.expand(-1, -1, x2_max_len)  # [batch_size, x1_seq_len, x2_seq_len]
        b_mask = x2_len.le(0.5).float() * -self.inf
        b_mask = b_mask.view(batch_size, -1, x2_max_len)
        b_mask = b_mask.expand(-1, x1_max_len, -1)  # [batch_size, x1_seq_len, x2_seq_len]

        attention_a = F.softmax(attention_matrix + a_mask, dim=2)  # [batch_size, x1_seq_len, x2_seq_len]
        attention_b = F.softmax(attention_matrix + b_mask, dim=1)  # [batch_size, x1_seq_len, x2_seq_len]

        out_x1 = torch.bmm(attention_a, in_x2)  # [batch_size, x1_seq_len, hidden_size]
        attention_b_t = torch.transpose(attention_b, 1, 2)
        out_x2 = torch.bmm(attention_b_t, in_x1)  # [batch_size, x2_seq_len, hidden_size]

        return out_x1, out_x2
