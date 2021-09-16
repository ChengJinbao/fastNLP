from torch import nn

from ..aggregator.attention import MultiHeadAtte
from ..dropout import TimestepDropout


class TransformerEncoder(nn.Module):
    """transformer的encoder模块，不包含embedding层

    :param num_layers: int, transformer的层数
    :param model_size: int, 输入维度的大小。同时也是输出维度的大小。
    :param inner_size: int, FFN层的hidden大小
    :param key_size: int, 每个head的维度大小。
    :param value_size: int，每个head中value的维度。
    :param num_head: int，head的数量。
    :param dropout: float。
    """
    class SubLayer(nn.Module):
        def __init__(self, model_size, inner_size, key_size, value_size, num_head, dropout=0.1):
            super(TransformerEncoder.SubLayer, self).__init__()
            self.atte = MultiHeadAtte(model_size, key_size, value_size, num_head, dropout)
            self.norm1 = nn.LayerNorm(model_size)
            self.ffn = nn.Sequential(nn.Linear(model_size, inner_size),
                                     nn.ReLU(),
                                     nn.Linear(inner_size, model_size),
                                     TimestepDropout(dropout),)
            self.norm2 = nn.LayerNorm(model_size)

        def forward(self, input, seq_mask=None, atte_mask_out=None):
            """

            :param input: [batch, seq_len, model_size]
            :param seq_mask: [batch, seq_len]
            :return: [batch, seq_len, model_size]
            """
            attention = self.atte(input, input, input, atte_mask_out)
            norm_atte = self.norm1(attention + input)
            attention *= seq_mask
            output = self.ffn(norm_atte)
            output = self.norm2(output + norm_atte)
            output *= seq_mask
            return output

    def __init__(self, num_layers, **kargs):
        super(TransformerEncoder, self).__init__()
        self.layers = nn.ModuleList([self.SubLayer(**kargs) for _ in range(num_layers)])

    def forward(self, x, seq_mask=None):
        """
        :param x: [batch, seq_len, model_size] 输入序列
        :param seq_mask: [batch, seq_len] 输入序列的padding mask
        :return: [batch, seq_len, model_size] 输出序列
        """
        output = x
        if seq_mask is None:
            atte_mask_out = None
        else:
            atte_mask_out = (seq_mask < 1)[:,None,:]
            seq_mask = seq_mask[:,:,None]
        for layer in self.layers:
            output = layer(output, seq_mask, atte_mask_out)
        return output
