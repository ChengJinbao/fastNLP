# python: 3.6
# encoding: utf-8

import torch
import torch.nn as nn

# import torch.nn.functional as F
import fastNLP.modules.encoder as encoder


class CNNText(torch.nn.Module):
    """
    Text classification model by character CNN, the implementation of paper
    'Yoon Kim. 2014. Convolution Neural Networks for Sentence
    Classification.'
    """

    def __init__(self, embed_num,
                 embed_dim,
                 num_classes,
                 kernel_nums=(3,4,5),
                 kernel_sizes=(3,4,5),
                 padding=0,
                 dropout=0.5):
        super(CNNText, self).__init__()

        # no support for pre-trained embedding currently
        self.embed = encoder.Embedding(embed_num, embed_dim)
        self.conv_pool = encoder.ConvMaxpool(
            in_channels=embed_dim,
            out_channels=kernel_nums,
            kernel_sizes=kernel_sizes,
            padding=padding)
        self.dropout = nn.Dropout(dropout)
        self.fc = encoder.Linear(sum(kernel_nums), num_classes)
        self._loss = nn.CrossEntropyLoss()

    def forward(self, word_seq):
        """
        :param word_seq: torch.LongTensor, [batch_size, seq_len]
        :return x: torch.LongTensor, [batch_size, num_classes]
        """
        x = self.embed(word_seq)  # [N,L] -> [N,L,C]
        x = self.conv_pool(x)  # [N,L,C] -> [N,C]
        x = self.dropout(x)
        x = self.fc(x)  # [N,C] -> [N, N_class]
        return {'output':x}

    def predict(self, word_seq):
        output = self(word_seq)
        _, predict = output.max(dim=1)
        return {'predict': predict}

    def get_loss(self, output, label_seq):
        return self._loss(output, label_seq)

    def evaluate(self, predict, label_seq):
        predict, label_seq = torch.stack(predict, dim=0), torch.stack(label_seq, dim=0)
        predict, label_seq = predict.squeeze(), label_seq.squeeze()
        correct = (predict == label_seq).long().sum().item()
        total = label_seq.size(0)
        return 1.0 * correct / total

