
import os

import torch
import torch.nn as nn
import numpy as np
import warnings

from ..core.vocabulary import Vocabulary
from ..io.file_utils import PRETRAIN_STATIC_FILES, _get_base_url, cached_path
from .embedding import TokenEmbedding
from ..modules.utils import _get_file_name_base_on_postfix

class StaticEmbedding(TokenEmbedding):
    """
    别名：:class:`fastNLP.embeddings.StaticEmbedding`   :class:`fastNLP.embeddings.static_embedding.StaticEmbedding`

    StaticEmbedding组件. 给定预训练embedding的名称或路径，根据vocab从embedding中抽取相应的数据(只会将出现在vocab中的词抽取出来，
    如果没有找到，则会随机初始化一个值(但如果该word是被标记为no_create_entry的话，则不会单独创建一个值，而是会被指向unk的index))。
    当前支持自动下载的预训练vector有以下的几种(待补充);

    Example::

        >>> vocab = Vocabulary().add_word_lst("The whether is good .".split())
        >>> embed = StaticEmbedding(vocab, model_dir_or_name='en-glove-50')

        >>> vocab = Vocabulary().add_word_lst(["The", 'the', "THE"])
        >>> embed = StaticEmbedding(vocab, model_dir_or_name="en-glove-50", lower=True)
        >>> # "the", "The", "THE"它们共用一个vector，且将使用"the"在预训练词表中寻找它们的初始化表示。

        >>> vocab = Vocabulary().add_word_lst(["The", "the", "THE"])
        >>> embed = StaticEmbedding(vocab, model_dir_or_name=None, embedding_dim=5, lower=True)
        >>> words = torch.LongTensor([[vocab.to_index(word) for word in ["The", "the", "THE"]]])
        >>> embed(words)
        >>> tensor([[[ 0.5773,  0.7251, -0.3104,  0.0777,  0.4849],
                     [ 0.5773,  0.7251, -0.3104,  0.0777,  0.4849],
                     [ 0.5773,  0.7251, -0.3104,  0.0777,  0.4849]]],
                   grad_fn=<EmbeddingBackward>)  # 每种word的输出是一致的。

    :param vocab: Vocabulary. 若该项为None则会读取所有的embedding。
    :param model_dir_or_name: 可以有两种方式调用预训练好的static embedding：第一种是传入embedding文件夹(文件夹下应该只有一个
        以.txt作为后缀的文件)或文件路径；第二种是传入embedding的名称，第二种情况将自动查看缓存中是否存在该模型，没有的话将自动下载。
        如果输入为None则使用embedding_dim的维度随机初始化一个embedding。
    :param int embedding_dim: 随机初始化的embedding的维度，仅在model_dir_or_name为None时有效。
    :param bool requires_grad: 是否需要gradient. 默认为True
    :param callable init_method: 如何初始化没有找到的值。可以使用torch.nn.init.*中各种方法。调用该方法时传入一个tensor对象。
    :param bool lower: 是否将vocab中的词语小写后再和预训练的词表进行匹配。如果你的词表中包含大写的词语，或者就是需要单独
        为大写的词语开辟一个vector表示，则将lower设置为False。
    :param float word_dropout: 以多大的概率将一个词替换为unk。这样既可以训练unk也是一定的regularize。
    :param float dropout: 以多大的概率对embedding的表示进行Dropout。0.1即随机将10%的值置为0。
    :param bool normalize: 是否对vector进行normalize，使得每个vector的norm为1。
    """
    def __init__(self, vocab: Vocabulary, model_dir_or_name: str='en', embedding_dim=100, requires_grad: bool=True,
                 init_method=None, lower=False, dropout=0, word_dropout=0, normalize=False):
        super(StaticEmbedding, self).__init__(vocab, word_dropout=word_dropout, dropout=dropout)

        # 得到cache_path
        if model_dir_or_name is None:
            assert embedding_dim>=1, "The dimension of embedding should be larger than 1."
            embedding_dim = int(embedding_dim)
            model_path = None
        elif model_dir_or_name.lower() in PRETRAIN_STATIC_FILES:
            PRETRAIN_URL = _get_base_url('static')
            model_name = PRETRAIN_STATIC_FILES[model_dir_or_name]
            model_url = PRETRAIN_URL + model_name
            model_path = cached_path(model_url)
            # 检查是否存在
        elif os.path.isfile(os.path.expanduser(os.path.abspath(model_dir_or_name))):
            model_path = model_dir_or_name
        elif os.path.isdir(os.path.expanduser(os.path.abspath(model_dir_or_name))):
            model_path = _get_file_name_base_on_postfix(model_dir_or_name, '.txt')
        else:
            raise ValueError(f"Cannot recognize {model_dir_or_name}.")

        # 读取embedding
        if lower:
            lowered_vocab = Vocabulary(padding=vocab.padding, unknown=vocab.unknown)
            for word, index in vocab:
                if not vocab._is_word_no_create_entry(word):
                    lowered_vocab.add_word(word.lower())  # 先加入需要创建entry的
            for word in vocab._no_create_word.keys():  # 不需要创建entry的
                if word in vocab:
                    lowered_word = word.lower()
                    if lowered_word not in lowered_vocab.word_count:
                        lowered_vocab.add_word(lowered_word)
                        lowered_vocab._no_create_word[lowered_word] += 1
            print(f"All word in vocab have been lowered. There are {len(vocab)} words, {len(lowered_vocab)} unique lowered "
                  f"words.")
            if model_path:
                embedding = self._load_with_vocab(model_path, vocab=lowered_vocab, init_method=init_method)
            else:
                embedding = self._randomly_init_embed(len(vocab), embedding_dim, init_method)
            # 需要适配一下
            if not hasattr(self, 'words_to_words'):
                self.words_to_words = torch.arange(len(lowered_vocab, )).long()
            if lowered_vocab.unknown:
                unknown_idx = lowered_vocab.unknown_idx
            else:
                unknown_idx = embedding.size(0) - 1  # 否则是最后一个为unknow
            words_to_words = nn.Parameter(torch.full((len(vocab),), fill_value=unknown_idx).long(),
                                          requires_grad=False)
            for word, index in vocab:
                if word not in lowered_vocab:
                    word = word.lower()
                    if lowered_vocab._is_word_no_create_entry(word):  # 如果不需要创建entry,已经默认unknown了
                        continue
                words_to_words[index] = self.words_to_words[lowered_vocab.to_index(word)]
            self.words_to_words = words_to_words
        else:
            if model_path:
                embedding = self._load_with_vocab(model_path, vocab=vocab, init_method=init_method)
            else:
                embedding = self._randomly_init_embed(len(vocab), embedding_dim, init_method)
        if normalize:
            embedding /= (torch.norm(embedding, dim=1, keepdim=True) + 1e-12)
        self.embedding = nn.Embedding(num_embeddings=embedding.shape[0], embedding_dim=embedding.shape[1],
                                      padding_idx=vocab.padding_idx,
                                      max_norm=None, norm_type=2, scale_grad_by_freq=False,
                                      sparse=False, _weight=embedding)
        self._embed_size = self.embedding.weight.size(1)
        self.requires_grad = requires_grad

    def _randomly_init_embed(self, num_embedding, embedding_dim, init_embed=None):
        """

        :param int num_embedding: embedding的entry的数量
        :param int embedding_dim: embedding的维度大小
        :param callable init_embed: 初始化方法
        :return: torch.FloatTensor
        """
        embed = torch.zeros(num_embedding, embedding_dim)

        if init_embed is None:
            nn.init.uniform_(embed, -np.sqrt(3/embedding_dim), np.sqrt(3/embedding_dim))
        else:
            init_embed(embed)

        return embed

    @property
    def requires_grad(self):
        """
        Embedding的参数是否允许优化。True: 所有参数运行优化; False: 所有参数不允许优化; None: 部分允许优化、部分不允许
        
        :return:
        """
        requires_grads = set([param.requires_grad for name, param in self.named_parameters()
                              if 'words_to_words' not in name])
        if len(requires_grads) == 1:
            return requires_grads.pop()
        else:
            return None

    @requires_grad.setter
    def requires_grad(self, value):
        for name, param in self.named_parameters():
            if 'words_to_words' in name:
                continue
            param.requires_grad = value

    def _load_with_vocab(self, embed_filepath, vocab, dtype=np.float32, padding='<pad>', unknown='<unk>',
                         error='ignore', init_method=None):
        """
        从embed_filepath这个预训练的词向量中抽取出vocab这个词表的词的embedding。EmbedLoader将自动判断embed_filepath是
        word2vec(第一行只有两个元素)还是glove格式的数据。

        :param str embed_filepath: 预训练的embedding的路径。
        :param vocab: 词表 :class:`~fastNLP.Vocabulary` 类型，读取出现在vocab中的词的embedding。
            没有出现在vocab中的词的embedding将通过找到的词的embedding的正态分布采样出来，以使得整个Embedding是同分布的。
        :param dtype: 读出的embedding的类型
        :param str padding: 词表中padding的token
        :param str unknown: 词表中unknown的token
        :param str error: `ignore` , `strict` ; 如果 `ignore` ，错误将自动跳过; 如果 `strict` , 错误将抛出。
            这里主要可能出错的地方在于词表有空行或者词表出现了维度不一致。
        :param init_method: 如何初始化没有找到的值。可以使用torch.nn.init.*中各种方法。默认使用torch.nn.init.zeros_
        :return torch.tensor:  shape为 [len(vocab), dimension], dimension由pretrain的embedding决定。
        """
        assert isinstance(vocab, Vocabulary), "Only fastNLP.Vocabulary is supported."
        if not os.path.exists(embed_filepath):
            raise FileNotFoundError("`{}` does not exist.".format(embed_filepath))
        with open(embed_filepath, 'r', encoding='utf-8') as f:
            line = f.readline().strip()
            parts = line.split()
            start_idx = 0
            if len(parts) == 2:
                dim = int(parts[1])
                start_idx += 1
            else:
                dim = len(parts) - 1
                f.seek(0)
            matrix = {}
            found_count = 0
            for idx, line in enumerate(f, start_idx):
                try:
                    parts = line.strip().split()
                    word = ''.join(parts[:-dim])
                    nums = parts[-dim:]
                    # 对齐unk与pad
                    if word == padding and vocab.padding is not None:
                        word = vocab.padding
                    elif word == unknown and vocab.unknown is not None:
                        word = vocab.unknown
                    if word in vocab:
                        index = vocab.to_index(word)
                        matrix[index] = torch.from_numpy(np.fromstring(' '.join(nums), sep=' ', dtype=dtype, count=dim))
                        found_count += 1
                except Exception as e:
                    if error == 'ignore':
                        warnings.warn("Error occurred at the {} line.".format(idx))
                    else:
                        print("Error occurred at the {} line.".format(idx))
                        raise e
            print("Found {} out of {} words in the pre-training embedding.".format(found_count, len(vocab)))
            for word, index in vocab:
                if index not in matrix and not vocab._is_word_no_create_entry(word):
                    if vocab.unknown_idx in matrix:  # 如果有unkonwn，用unknown初始化
                        matrix[index] = matrix[vocab.unknown_idx]
                    else:
                        matrix[index] = None

            vectors = self._randomly_init_embed(len(matrix), dim, init_method)

            if vocab._no_create_word_length>0:
                if vocab.unknown is None:  # 创建一个专门的unknown
                    unknown_idx = len(matrix)
                    vectors = torch.cat((vectors, torch.zeros(1, dim)), dim=0).contiguous()
                else:
                    unknown_idx = vocab.unknown_idx
                words_to_words = nn.Parameter(torch.full((len(vocab),), fill_value=unknown_idx).long(),
                                              requires_grad=False)
                for order, (index, vec) in enumerate(matrix.items()):
                    if vec is not None:
                        vectors[order] = vec
                    words_to_words[index] = order
                self.words_to_words = words_to_words
            else:
                for index, vec in matrix.items():
                    if vec is not None:
                        vectors[index] = vec

            return vectors

    def forward(self, words):
        """
        传入words的index

        :param words: torch.LongTensor, [batch_size, max_len]
        :return: torch.FloatTensor, [batch_size, max_len, embed_size]
        """
        if hasattr(self, 'words_to_words'):
            words = self.words_to_words[words]
        words = self.drop_word(words)
        words = self.embedding(words)
        words = self.dropout(words)
        return words
