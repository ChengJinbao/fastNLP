import torch
import torch.nn.functional as F
from torch import nn


class ConvCharEmbedding(nn.Module):

    def __init__(self, char_emb_size, feature_maps=(40, 30, 30), kernels=(3, 4, 5)):
        """
        Character Level Word Embedding
        :param char_emb_size: the size of character level embedding,
            say 26 characters, each embedded to 50 dim vector, then the input_size is 50.
        :param feature_maps: table of feature maps (for each kernel width)
        :param kernels: table of kernel widths
        """
        super(ConvCharEmbedding, self).__init__()
        self.convs = nn.ModuleList([
            nn.Conv2d(1, feature_maps[i], kernel_size=(char_emb_size, kernels[i]), bias=True, padding=(0, 4))
            for i in range(len(kernels))])

    def forward(self, x):
        """
        :param x: [batch_size * sent_length, word_length, char_emb_size]
        :return: [batch_size * sent_length, sum(feature_maps), 1]
        """
        x = x.contiguous().view(x.size(0), 1, x.size(1), x.size(2))  # [batch_size*sent_length, channel, width, height]
        x = x.transpose(2, 3)  # [batch_size*sent_length, channel, height, width]
        return self.convolute(x).unsqueeze(2)

    def convolute(self, x):
        feats = []
        for conv in self.convs:
            y = conv(x)  # [batch_size*sent_length, feature_maps[i], 1, width - kernels[i] + 1]
            y = torch.squeeze(y, 2)  # [batch_size*sent_length, feature_maps[i], width - kernels[i] + 1]
            y = F.tanh(y)
            y, __ = torch.max(y, 2)  # [batch_size*sent_length, feature_maps[i]]
            feats.append(y)
        return torch.cat(feats, 1)  # [batch_size*sent_length, sum(feature_maps)]


class LSTMCharEmbedding(nn.Module):
    """
    Character Level Word Embedding with LSTM
    :param char_emb_size: the size of character level embedding,
        say 26 characters, each embedded to 50 dim vector, then the input_size is 50.
    """

    def __init__(self, char_emb_size, hidden_size=None):
        super(LSTMCharEmbedding, self).__init__()
        self.hidden_size = char_emb_size if hidden_size is None else hidden_size

        self.lstm = nn.LSTM(input_size=char_emb_size,
                            hidden_size=self.hidden_size,
                            num_layers=1,
                            bias=True,
                            batch_first=True)

    def forward(self, x):
        """
        :param x:[ n_batch*n_word, word_length, char_emb_size]
        :return: [ n_batch*n_word, char_emb_size]
        """
        batch_size = x.shape[0]
        h0 = torch.empty(1, batch_size, self.hidden_size)
        h0 = nn.init.orthogonal_(h0)
        c0 = torch.empty(1, batch_size, self.hidden_size)
        c0 = nn.init.orthogonal_(c0)

        _, hidden = self.lstm(x, (h0, c0))
        return hidden[0].squeeze().unsqueeze(2)


if __name__ == "__main__":
    batch_size = 128
    char_emb = 100
    word_length = 1
    x = torch.Tensor(batch_size, char_emb, word_length)
    x = x.transpose(1, 2)
    cce = ConvCharEmbedding(char_emb)
    y = cce(x)
    print("CNN Char Emb input: ", x.shape)
    print("CNN Char Emb output: ", y.shape)  # [128, 100]

    lce = LSTMCharEmbedding(char_emb)
    o = lce(x)
    print("LSTM Char Emb input: ", x.shape)
    print("LSTM Char Emb size: ", o.shape)
