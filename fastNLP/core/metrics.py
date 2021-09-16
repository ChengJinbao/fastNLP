import inspect
from collections import defaultdict

import numpy as np
import torch

from fastNLP.core.utils import CheckError
from fastNLP.core.utils import CheckRes
from fastNLP.core.utils import _build_args
from fastNLP.core.utils import _check_arg_dict_list
from fastNLP.core.utils import get_func_signature
from fastNLP.core.utils import seq_lens_to_masks
from fastNLP.core.vocabulary import Vocabulary


class MetricBase(object):
    """Base class for all metrics.

    所有的传入到Trainer, Tester的Metric需要继承自该对象。需要覆盖写入evaluate(), get_metric()方法。
        evaluate(xxx)中传入的是一个batch的数据。
        get_metric(xxx)当所有数据处理完毕，调用该方法得到最终的metric值
    以分类问题中，Accuracy计算为例
    假设model的forward返回dict中包含'pred'这个key, 并且该key需要用于Accuracy
    class Model(nn.Module):
        def __init__(xxx):
            # do something
        def forward(self, xxx):
            # do something
            return {'pred': pred, 'other_keys':xxx} # pred's shape: batch_size x num_classes
    假设dataset中'label'这个field是需要预测的值，并且该field被设置为了target
    对应的AccMetric可以按如下的定义
    # version1, 只使用这一次
    class AccMetric(MetricBase):
        def __init__(self):
            super().__init__()

            # 根据你的情况自定义指标
            self.corr_num = 0
            self.total = 0

        def evaluate(self, label, pred): # 这里的名称需要和dataset中target field与model返回的key是一样的，不然找不到对应的value
            # dev或test时，每个batch结束会调用一次该方法，需要实现如何根据每个batch累加metric
            self.total += label.size(0)
            self.corr_num += label.eq(pred).sum().item()

        def get_metric(self, reset=True): # 在这里定义如何计算metric
            acc = self.corr_num/self.total
            if reset: # 是否清零以便重新计算
                self.corr_num = 0
                self.total = 0
            return {'acc': acc} # 需要返回一个dict，key为该metric的名称，该名称会显示到Trainer的progress bar中


    # version2，如果需要复用Metric，比如下一次使用AccMetric时，dataset中目标field不叫label而叫y，或者model的输出不是pred
    class AccMetric(MetricBase):
        def __init__(self, label=None, pred=None):
            # 假设在另一场景使用时，目标field叫y，model给出的key为pred_y。则只需要在初始化AccMetric时，
            #   acc_metric = AccMetric(label='y', pred='pred_y')即可。
            # 当初始化为acc_metric = AccMetric()，即label=None, pred=None, fastNLP会直接使用'label', 'pred'作为key去索取对
            #   应的的值
            super().__init__()
            self._init_param_map(label=label, pred=pred) # 该方法会注册label和pred. 仅需要注册evaluate()方法会用到的参数名即可
            # 如果没有注册该则效果与version1就是一样的

            # 根据你的情况自定义指标
            self.corr_num = 0
            self.total = 0

        def evaluate(self, label, pred): # 这里的参数名称需要和self._init_param_map()注册时一致。
            # dev或test时，每个batch结束会调用一次该方法，需要实现如何根据每个batch累加metric
            self.total += label.size(0)
            self.corr_num += label.eq(pred).sum().item()

        def get_metric(self, reset=True): # 在这里定义如何计算metric
            acc = self.corr_num/self.total
            if reset: # 是否清零以便重新计算
                self.corr_num = 0
                self.total = 0
            return {'acc': acc} # 需要返回一个dict，key为该metric的名称，该名称会显示到Trainer的progress bar中


    ``MetricBase`` handles validity check of its input dictionaries - ``pred_dict`` and ``target_dict``.
    ``pred_dict`` is the output of ``forward()`` or prediction function of a model.
    ``target_dict`` is the ground truth from DataSet where ``is_target`` is set ``True``.
    ``MetricBase`` will do the following type checks:

        1. whether self.evaluate has varargs, which is not supported.
        2. whether params needed by self.evaluate is not included in ``pred_dict``, ``target_dict``.
        3. whether params needed by self.evaluate duplicate in ``pred_dict``, ``target_dict``.

    Besides, before passing params into self.evaluate, this function will filter out params from output_dict and
    target_dict which are not used in self.evaluate. (but if **kwargs presented in self.evaluate, no filtering
    will be conducted.)

    """
    def __init__(self):
        self.param_map = {}  # key is param in function, value is input param.
        self._checked = False

    def evaluate(self, *args, **kwargs):
        raise NotImplementedError

    def _init_param_map(self, key_map=None, **kwargs):
        """Check the validity of key_map and other param map. Add these into self.param_map

        :param key_map: dict
        :param kwargs:
        :return: None
        """
        value_counter = defaultdict(set)
        if key_map is not None:
            if not isinstance(key_map, dict):
                raise TypeError("key_map must be `dict`, got {}.".format(type(key_map)))
            for key, value in key_map.items():
                if value is None:
                    self.param_map[key] = key
                    continue
                if not isinstance(key, str):
                    raise TypeError(f"key in key_map must be `str`, not `{type(key)}`.")
                if not isinstance(value, str):
                    raise TypeError(f"value in key_map must be `str`, not `{type(value)}`.")
                self.param_map[key] = value
                value_counter[value].add(key)
        for key, value in kwargs.items():
            if value is None:
                self.param_map[key] = key
                continue
            if not isinstance(value, str):
                raise TypeError(f"in {key}={value}, value must be `str`, not `{type(value)}`.")
            self.param_map[key] = value
            value_counter[value].add(key)
        for value, key_set in value_counter.items():
            if len(key_set) > 1:
                raise ValueError(f"Several parameters:{key_set} are provided with one output {value}.")

        # check consistence between signature and param_map
        func_spect = inspect.getfullargspec(self.evaluate)
        func_args = [arg for arg in func_spect.args if arg != 'self']
        for func_param, input_param in self.param_map.items():
            if func_param not in func_args:
                raise NameError(
                    f"Parameter `{func_param}` is not in {get_func_signature(self.evaluate)}. Please check the "
                    f"initialization parameters, or change its signature.")

    def get_metric(self, reset=True):
        raise NotImplemented

    def __call__(self, pred_dict, target_dict):
        """

        This method will call self.evaluate method.
        Before calling self.evaluate, it will first check the validity of output_dict, target_dict
            (1) whether params needed by self.evaluate is not included in output_dict,target_dict.
            (2) whether params needed by self.evaluate duplicate in pred_dict, target_dict
            (3) whether params in output_dict, target_dict are not used by evaluate.(Might cause warning)
        Besides, before passing params into self.evaluate, this function will filter out params from output_dict and
            target_dict which are not used in self.evaluate. (but if **kwargs presented in self.evaluate, no filtering
            will be conducted.)
        :param pred_dict: usually the output of forward or prediction function
        :param target_dict: usually features set as target..
        :return:
        """
        if not callable(self.evaluate):
            raise TypeError(f"{self.__class__.__name__}.evaluate has to be callable, not {type(self.evaluate)}.")

        if not self._checked:
            # 1. check consistence between signature and param_map
            func_spect = inspect.getfullargspec(self.evaluate)
            func_args = set([arg for arg in func_spect.args if arg != 'self'])
            for func_arg, input_arg in self.param_map.items():
                if func_arg not in func_args:
                    raise NameError(f"`{func_arg}` not in {get_func_signature(self.evaluate)}.")

            # 2. only part of the param_map are passed, left are not
            for arg in func_args:
                if arg not in self.param_map:
                    self.param_map[arg] = arg  # This param does not need mapping.
            self._evaluate_args = func_args
            self._reverse_param_map = {input_arg: func_arg for func_arg, input_arg in self.param_map.items()}

        # need to wrap inputs in dict.
        mapped_pred_dict = {}
        mapped_target_dict = {}
        duplicated = []
        for input_arg in set(list(pred_dict.keys()) + list(target_dict.keys())):
            not_duplicate_flag = 0
            if input_arg in self._reverse_param_map:
                mapped_arg = self._reverse_param_map[input_arg]
                not_duplicate_flag += 1
            else:
                mapped_arg = input_arg
            if input_arg in pred_dict:
                mapped_pred_dict[mapped_arg] = pred_dict[input_arg]
                not_duplicate_flag += 1
            if input_arg in target_dict:
                mapped_target_dict[mapped_arg] = target_dict[input_arg]
                not_duplicate_flag += 1
            if not_duplicate_flag == 3:
                duplicated.append(input_arg)

        # missing
        if not self._checked:
            check_res = _check_arg_dict_list(self.evaluate, [mapped_pred_dict, mapped_target_dict])
            # only check missing.
            # replace missing.
            missing = check_res.missing
            replaced_missing = list(missing)
            for idx, func_arg in enumerate(missing):
                # Don't delete `` in this information, nor add ``
                replaced_missing[idx] = f"{self.param_map[func_arg]}" + f"(assign to `{func_arg}` " \
                                                                        f"in `{self.__class__.__name__}`)"

            check_res = CheckRes(missing=replaced_missing,
                                 unused=check_res.unused,
                                 duplicated=duplicated,
                                 required=check_res.required,
                                 all_needed=check_res.all_needed,
                                 varargs=check_res.varargs)

            if check_res.missing or check_res.duplicated:
                raise CheckError(check_res=check_res,
                                 func_signature=get_func_signature(self.evaluate))
        refined_args = _build_args(self.evaluate, **mapped_pred_dict, **mapped_target_dict)

        self.evaluate(**refined_args)
        self._checked = True

        return


class AccuracyMetric(MetricBase):
    """Accuracy Metric

    """
    def __init__(self, pred=None, target=None, seq_lens=None):
        super().__init__()

        self._init_param_map(pred=pred, target=target, seq_lens=seq_lens)

        self.total = 0
        self.acc_count = 0

    def evaluate(self, pred, target, seq_lens=None):
        """

        :param pred: . Element's shape can be: torch.Size([B,]), torch.Size([B, n_classes]), torch.Size([B, max_len]),
                torch.Size([B, max_len, n_classes])
        :param target: Element's can be: torch.Size([B,]), torch.Size([B,]), torch.Size([B, max_len]),
                torch.Size([B, max_len])
        :param seq_lens: Element's can be: None, None, torch.Size([B], torch.Size([B]). ignored if masks are provided.

        """
        # TODO 这里报错需要更改，因为pred是啥用户并不知道。需要告知用户真实的value
        if not isinstance(pred, torch.Tensor):
            raise TypeError(f"`pred` in {get_func_signature(self.evaluate)} must be torch.Tensor,"
                            f"got {type(pred)}.")
        if not isinstance(target, torch.Tensor):
            raise TypeError(f"`target` in {get_func_signature(self.evaluate)} must be torch.Tensor,"
                            f"got {type(target)}.")

        if seq_lens is not None and not isinstance(seq_lens, torch.Tensor):
            raise TypeError(f"`seq_lens` in {get_func_signature(self.evaluate)} must be torch.Tensor,"
                            f"got {type(seq_lens)}.")

        if seq_lens is not None:
            masks = seq_lens_to_masks(seq_lens=seq_lens)
        else:
            masks = None

        if pred.size() == target.size():
            pass
        elif len(pred.size()) == len(target.size()) + 1:
            pred = pred.argmax(dim=-1)
        else:
            raise RuntimeError(f"In {get_func_signature(self.evaluate)}, when pred have "
                               f"size:{pred.size()}, target should have size: {pred.size()} or "
                               f"{pred.size()[:-1]}, got {target.size()}.")

        target = target.to(pred)
        if masks is not None:
            self.acc_count += torch.sum(torch.eq(pred, target).masked_fill(masks, 0)).item()
            self.total += torch.sum(masks).item()
        else:
            self.acc_count += torch.sum(torch.eq(pred, target)).item()
            self.total += np.prod(list(pred.size()))

    def get_metric(self, reset=True):
        """Returns computed metric.

        :param bool reset: whether to recount next time.
        :return evaluate_result: {"acc": float}
        """
        evaluate_result = {'acc': round(float(self.acc_count) / (self.total + 1e-12), 6)}
        if reset:
            self.acc_count = 0
            self.total = 0
        return evaluate_result

def bmes_tag_to_spans(tags, ignore_labels=None):
    """
    给定一个tags的lis，比如['S', 'B-singer', 'M-singer', 'E-singer', 'S', 'S']。
    返回[('', (0, 1)), ('singer', (1, 4)), ('', (4, 5)), ('', (5, 6))] (左闭右开区间)

    :param tags: List[str],
    :param ignore_labels: List[str], 在该list中的label将被忽略
    :return: List[Tuple[str, List[int, int]]]. [(label，[start, end])]
    """
    ignore_labels = set(ignore_labels) if ignore_labels else set()

    spans = []
    prev_bmes_tag = None
    for idx, tag in enumerate(tags):
        tag = tag.lower()
        bmes_tag, label = tag[:1], tag[2:]
        if bmes_tag in ('b', 's'):
            spans.append((label, [idx, idx]))
        elif bmes_tag in ('m', 'e') and prev_bmes_tag in ('b', 'm') and label==spans[-1][0]:
            spans[-1][1][1] = idx
        else:
            spans.append((label, [idx, idx]))
        prev_bmes_tag = bmes_tag
    return [(span[0], (span[1][0], span[1][1]+1))
                    for span in spans
                        if span[0] not in ignore_labels
            ]

def bmeso_tag_to_spans(tags, ignore_labels=None):
    """
    给定一个tags的lis，比如['O', 'B-singer', 'M-singer', 'E-singer', 'O', 'O']。
    返回[('singer', (1, 4))] (左闭右开区间)

    :param tags: List[str],
    :param ignore_labels: List[str], 在该list中的label将被忽略
    :return: List[Tuple[str, List[int, int]]]. [(label，[start, end])]
    """
    ignore_labels = set(ignore_labels) if ignore_labels else set()

    spans = []
    prev_bmes_tag = None
    for idx, tag in enumerate(tags):
        tag = tag.lower()
        bmes_tag, label = tag[:1], tag[2:]
        if bmes_tag in ('b', 's'):
            spans.append((label, [idx, idx]))
        elif bmes_tag in ('m', 'e') and prev_bmes_tag in ('b', 'm') and label==spans[-1][0]:
            spans[-1][1][1] = idx
        elif bmes_tag == 'o':
            pass
        else:
            spans.append((label, [idx, idx]))
        prev_bmes_tag = bmes_tag
    return [(span[0], (span[1][0], span[1][1]+1))
                    for span in spans
                        if span[0] not in ignore_labels
            ]

def bio_tag_to_spans(tags, ignore_labels=None):
    """
    给定一个tags的lis，比如['O', 'B-singer', 'I-singer', 'I-singer', 'O', 'O']。
        返回[('singer', (1, 4))] (左闭右开区间)

    :param tags: List[str],
    :param ignore_labels: List[str], 在该list中的label将被忽略
    :return: List[Tuple[str, List[int, int]]]. [(label，[start, end])]
    """
    ignore_labels = set(ignore_labels) if ignore_labels else set()

    spans = []
    prev_bio_tag = None
    for idx, tag in enumerate(tags):
        tag = tag.lower()
        bio_tag, label = tag[:1], tag[2:]
        if bio_tag == 'b':
            spans.append((label, [idx, idx]))
        elif bio_tag == 'i' and prev_bio_tag in ('b', 'i') and label==spans[-1][0]:
            spans[-1][1][1] = idx
        elif bio_tag == 'o': # o tag does not count
            pass
        else:
            spans.append((label, [idx, idx]))
        prev_bio_tag = bio_tag
    return [(span[0], (span[1][0], span[1][1]+1))
                    for span in spans
                        if span[0] not in ignore_labels]


class SpanFPreRecMetric(MetricBase):
    """
    在序列标注问题中，以span的方式计算F, pre, rec.
    比如中文Part of speech中，会以character的方式进行标注，句子'中国在亚洲'对应的POS可能为(以BMES为例)
        ['B-NN', 'E-NN', 'S-DET', 'B-NN', 'E-NN']。该metric就是为类似情况下的F1计算。
    最后得到的metric结果为
    {
        'f': xxx, # 这里使用f考虑以后可以计算f_beta值
        'pre': xxx,
        'rec':xxx
    }
    若only_gross=False, 即还会返回各个label的metric统计值
        {
        'f': xxx,
        'pre': xxx,
        'rec':xxx,
        'f-label': xxx,
        'pre-label': xxx,
        'rec-label':xxx,
        ...
    }

    """
    def __init__(self, tag_vocab, pred=None, target=None, seq_lens=None, encoding_type='bio', ignore_labels=None,
                  only_gross=True, f_type='micro', beta=1):
        """

        :param tag_vocab: Vocabulary, 标签的vocabulary。支持的标签为"B"(没有label)；或"B-xxx"(xxx为某种label，比如POS中的NN)，
            在解码时，会将相同xxx的认为是同一个label，比如['B-NN', 'E-NN']会被合并为一个'NN'.
        :param pred: str, 用该key在evaluate()时从传入dict中取出prediction数据。 为None，则使用'pred'取数据
        :param target: str, 用该key在evaluate()时从传入dict中取出target数据。 为None，则使用'target'取数据
        :param seq_lens: str, 用该key在evaluate()时从传入dict中取出sequence length数据。为None，则使用'seq_lens'取数据。
        :param encoding_type: str, 目前支持bio, bmes
        :param ignore_labels, List[str]. 这个list中的class不会被用于计算。例如在POS tagging时传入['NN']，则不会计算'NN'这
            个label
        :param only_gross, bool. 是否只计算总的f1, precision, recall的值；如果为False，不仅返回总的f1, pre, rec, 还会返回每个
            label的f1, pre, rec
        :param f_type, str. 'micro'或'macro'. 'micro':通过先计算总体的TP，FN和FP的数量，再计算f, precision, recall; 'macro':
            分布计算每个类别的f, precision, recall，然后做平均（各类别f的权重相同）
        :param beta, float. f_beta分数，f_beta = (1 + beta^2)*(pre*rec)/(beta^2*pre + rec). 常用为beta=0.5, 1, 2. 若为0.5
            则精确率的权重高于召回率；若为1，则两者平等；若为2，则召回率权重高于精确率。
        """
        encoding_type = encoding_type.lower()

        if not isinstance(tag_vocab, Vocabulary):
            raise TypeError("tag_vocab can only be fastNLP.Vocabulary, not {}.".format(type(tag_vocab)))
        if f_type not in ('micro', 'macro'):
            raise ValueError("f_type only supports `micro` or `macro`', got {}.".format(f_type))

        self.encoding_type = encoding_type
        if self.encoding_type == 'bmes':
            self.tag_to_span_func = bmes_tag_to_spans
        elif self.encoding_type == 'bio':
            self.tag_to_span_func = bio_tag_to_spans
        elif self.encoding_type == 'bmeso':
            self.tag_to_span_func = bmeso_tag_to_spans
        else:
            raise ValueError("Only support 'bio', 'bmes', 'bmeso' type.")

        self.ignore_labels = ignore_labels
        self.f_type = f_type
        self.beta = beta
        self.beta_square = self.beta**2
        self.only_gross = only_gross

        super().__init__()
        self._init_param_map(pred=pred, target=target, seq_lens=seq_lens)

        self.tag_vocab = tag_vocab

        self._true_positives = defaultdict(int)
        self._false_positives = defaultdict(int)
        self._false_negatives = defaultdict(int)

    def evaluate(self, pred, target, seq_lens):
        """
        A lot of design idea comes from allennlp's measure
        :param pred:
        :param target:
        :param seq_lens:
        :return:
        """
        if not isinstance(pred, torch.Tensor):
            raise TypeError(f"`pred` in {get_func_signature(self.evaluate)} must be torch.Tensor,"
                            f"got {type(pred)}.")
        if not isinstance(target, torch.Tensor):
            raise TypeError(f"`target` in {get_func_signature(self.evaluate)} must be torch.Tensor,"
                            f"got {type(target)}.")

        if not isinstance(seq_lens, torch.Tensor):
            raise TypeError(f"`seq_lens` in {get_func_signature(self.evaluate)} must be torch.Tensor,"
                            f"got {type(seq_lens)}.")

        if pred.size() == target.size() and len(target.size()) == 2:
            pass
        elif len(pred.size()) == len(target.size()) + 1 and len(target.size()) == 2:
            pred = pred.argmax(dim=-1)
            num_classes = pred.size(-1)
            if (target >= num_classes).any():
                raise ValueError("A gold label passed to SpanBasedF1Metric contains an "
                                 "id >= {}, the number of classes.".format(num_classes))
        else:
            raise RuntimeError(f"In {get_func_signature(self.evaluate)}, when pred have "
                               f"size:{pred.size()}, target should have size: {pred.size()} or "
                               f"{pred.size()[:-1]}, got {target.size()}.")

        batch_size = pred.size(0)
        for i in range(batch_size):
            pred_tags = pred[i, :int(seq_lens[i])].tolist()
            gold_tags = target[i, :int(seq_lens[i])].tolist()

            pred_str_tags = [self.tag_vocab.to_word(tag) for tag in pred_tags]
            gold_str_tags = [self.tag_vocab.to_word(tag) for tag in gold_tags]

            pred_spans = self.tag_to_span_func(pred_str_tags, ignore_labels=self.ignore_labels)
            gold_spans = self.tag_to_span_func(gold_str_tags, ignore_labels=self.ignore_labels)

            for span in pred_spans:
                if span in gold_spans:
                    self._true_positives[span[0]] += 1
                    gold_spans.remove(span)
                else:
                    self._false_positives[span[0]] += 1
            for span in gold_spans:
                self._false_negatives[span[0]] += 1

    def get_metric(self, reset=True):
        evaluate_result = {}
        if not self.only_gross or self.f_type=='macro':
            tags = set(self._false_negatives.keys())
            tags.update(set(self._false_positives.keys()))
            tags.update(set(self._true_positives.keys()))
            f_sum = 0
            pre_sum = 0
            rec_sum = 0
            for tag in tags:
                tp = self._true_positives[tag]
                fn = self._false_negatives[tag]
                fp = self._false_positives[tag]
                f, pre, rec = self._compute_f_pre_rec(tp, fn, fp)
                f_sum += f
                pre_sum += pre
                rec_sum + rec
                if not self.only_gross and tag!='': # tag!=''防止无tag的情况
                    f_key = 'f-{}'.format(tag)
                    pre_key = 'pre-{}'.format(tag)
                    rec_key = 'rec-{}'.format(tag)
                    evaluate_result[f_key] = f
                    evaluate_result[pre_key] = pre
                    evaluate_result[rec_key] = rec

            if self.f_type == 'macro':
                evaluate_result['f'] = f_sum/len(tags)
                evaluate_result['pre'] = pre_sum/len(tags)
                evaluate_result['rec'] = rec_sum/len(tags)

        if self.f_type == 'micro':
            f, pre, rec = self._compute_f_pre_rec(sum(self._true_positives.values()),
                                                  sum(self._false_negatives.values()),
                                                  sum(self._false_positives.values()))
            evaluate_result['f'] = round(f, 6)
            evaluate_result['pre'] = round(pre, 6)
            evaluate_result['rec'] = round(rec, 6)

        if reset:
            self._true_positives = defaultdict(int)
            self._false_positives = defaultdict(int)
            self._false_negatives = defaultdict(int)

        return evaluate_result

    def _compute_f_pre_rec(self, tp, fn, fp):
        """

        :param tp: int, true positive
        :param fn: int, false negative
        :param fp: int, false positive
        :return: (f, pre, rec)
        """
        pre = tp / (fp + tp + 1e-13)
        rec = tp / (fn + tp + 1e-13)
        f = (1 + self.beta_square) * pre * rec / (self.beta_square * pre + rec + 1e-13)

        return f, pre, rec

class BMESF1PreRecMetric(MetricBase):
    """
    按照BMES标注方式计算f1, precision, recall。由于可能存在非法tag，比如"BS"，所以需要用以下的表格做转换，cur_B意思是当前tag是B，
        next_B意思是后一个tag是B。则cur_B=S，即将当前被predict是B的tag标为S；next_M=B, 即将后一个被predict是M的tag标为B
        |       |  next_B |  next_M  |  next_E  |  next_S |   end   |
        |:-----:|:-------:|:--------:|:--------:|:-------:|:-------:|
        | start |   合法  | next_M=B | next_E=S |   合法  |    -    |
        | cur_B | cur_B=S |   合法   |   合法   | cur_B=S | cur_B=S |
        | cur_M | cur_M=E |   合法   |   合法   | cur_M=E | cur_M=E |
        | cur_E |   合法  | next_M=B | next_E=S |   合法  |   合法  |
        | cur_S |   合法  | next_M=B | next_E=S |   合法  |   合法  |
    举例：
        prediction为BSEMS，会被认为是SSSSS.

    本Metric不检验target的合法性，请务必保证target的合法性。
        pred的形状应该为(batch_size, max_len) 或 (batch_size, max_len, 4)。
        target形状为 (batch_size, max_len)
        seq_lens形状为 (batch_size, )

    """

    def __init__(self, b_idx=0, m_idx=1, e_idx=2, s_idx=3, pred=None, target=None, seq_lens=None):
        """
        需要申明BMES这四种tag中，各种tag对应的idx。所有不为b_idx, m_idx, e_idx, s_idx的数字都认为是s_idx。

        :param b_idx: int, Begin标签所对应的tag idx.
        :param m_idx: int, Middle标签所对应的tag idx.
        :param e_idx: int, End标签所对应的tag idx.
        :param s_idx: int, Single标签所对应的tag idx
        :param pred: str, 用该key在evaluate()时从传入dict中取出prediction数据。 为None，则使用'pred'取数据
        :param target: str, 用该key在evaluate()时从传入dict中取出target数据。 为None，则使用'target'取数据
        :param seq_lens: str, 用该key在evaluate()时从传入dict中取出seqence length数据。为None，则使用'seq_lens'取数据。
        """
        super().__init__()

        self._init_param_map(pred=pred, target=target, seq_lens=seq_lens)

        self.yt_wordnum = 0
        self.yp_wordnum = 0
        self.corr_num = 0

        self.b_idx = b_idx
        self.m_idx = m_idx
        self.e_idx = e_idx
        self.s_idx = s_idx
        # 还原init处介绍的矩阵
        self._valida_matrix = {
            -1: [(-1, -1), (1, self.b_idx), (1, self.s_idx), (-1, -1)], # magic start idx
            self.b_idx:[(0, self.s_idx), (-1, -1), (-1, -1), (0, self.s_idx), (0, self.s_idx)],
            self.m_idx:[(0, self.e_idx), (-1, -1), (-1, -1), (0, self.e_idx), (0, self.e_idx)],
            self.e_idx:[(-1, -1), (1, self.b_idx), (1, self.s_idx), (-1, -1), (-1, -1)],
            self.s_idx:[(-1, -1), (1, self.b_idx), (1, self.s_idx), (-1, -1), (-1, -1)],
        }

    def _validate_tags(self, tags):
        """
        给定一个tag的Tensor，返回合法tag

        :param tags: Tensor, shape: (seq_len, )
        :return: 返回修改为合法tag的list
        """
        assert len(tags)!=0
        assert isinstance(tags, torch.Tensor) and len(tags.size())==1
        padded_tags = [-1, *tags.tolist(), -1]
        for idx in range(len(padded_tags)-1):
            cur_tag = padded_tags[idx]
            if cur_tag not in self._valida_matrix:
                cur_tag = self.s_idx
            if padded_tags[idx+1] not in self._valida_matrix:
                padded_tags[idx+1] = self.s_idx
            next_tag = padded_tags[idx+1]
            shift_tag = self._valida_matrix[cur_tag][next_tag]
            if shift_tag[0]!=-1:
                padded_tags[idx+shift_tag[0]] = shift_tag[1]

        return padded_tags[1:-1]

    def evaluate(self, pred, target, seq_lens):
        if not isinstance(pred, torch.Tensor):
            raise TypeError(f"`pred` in {get_func_signature(self.evaluate)} must be torch.Tensor,"
                            f"got {type(pred)}.")
        if not isinstance(target, torch.Tensor):
            raise TypeError(f"`target` in {get_func_signature(self.evaluate)} must be torch.Tensor,"
                            f"got {type(target)}.")

        if not isinstance(seq_lens, torch.Tensor):
            raise TypeError(f"`seq_lens` in {get_func_signature(self.evaluate)} must be torch.Tensor,"
                            f"got {type(seq_lens)}.")

        if pred.size() == target.size() and len(target.size()) == 2:
            pass
        elif len(pred.size()) == len(target.size()) + 1 and len(target.size()) == 2:
            pred = pred.argmax(dim=-1)
        else:
            raise RuntimeError(f"In {get_func_signature(self.evaluate)}, when pred have "
                               f"size:{pred.size()}, target should have size: {pred.size()} or "
                               f"{pred.size()[:-1]}, got {target.size()}.")

        for idx in range(len(pred)):
            seq_len = seq_lens[idx]
            target_tags = target[idx][:seq_len].tolist()
            pred_tags = pred[idx][:seq_len]
            pred_tags = self._validate_tags(pred_tags)
            start_idx = 0
            for t_idx, (t_tag, p_tag) in enumerate(zip(target_tags, pred_tags)):
                if t_tag in (self.s_idx,  self.e_idx):
                    self.yt_wordnum += 1
                    corr_flag = True
                    for i in range(start_idx, t_idx+1):
                        if target_tags[i]!=pred_tags[i]:
                            corr_flag = False
                    if corr_flag:
                        self.corr_num += 1
                    start_idx = t_idx + 1
                if p_tag in (self.s_idx, self.e_idx):
                    self.yp_wordnum += 1

    def get_metric(self, reset=True):
        P = self.corr_num / (self.yp_wordnum + 1e-12)
        R = self.corr_num / (self.yt_wordnum + 1e-12)
        F = 2 * P * R / (P + R + 1e-12)
        evaluate_result = {'f': round(F, 6), 'pre':round(P, 6), 'rec': round(R, 6)}
        if reset:
            self.yp_wordnum = 0
            self.yt_wordnum = 0
            self.corr_num = 0
        return evaluate_result


def _prepare_metrics(metrics):
    """

    Prepare list of Metric based on input
    :param metrics:
    :return: List[fastNLP.MetricBase]
    """
    _metrics = []
    if metrics:
        if isinstance(metrics, list):
            for metric in metrics:
                if isinstance(metric, type):
                    metric = metric()
                if isinstance(metric, MetricBase):
                    metric_name = metric.__class__.__name__
                    if not callable(metric.evaluate):
                        raise TypeError(f"{metric_name}.evaluate must be callable, got {type(metric.evaluate)}.")
                    if not callable(metric.get_metric):
                        raise TypeError(f"{metric_name}.get_metric must be callable, got {type(metric.get_metric)}.")
                    _metrics.append(metric)
                else:
                    raise TypeError(
                        f"The type of metric in metrics must be `fastNLP.MetricBase`, not `{type(metric)}`.")
        elif isinstance(metrics, MetricBase):
            _metrics = [metrics]
        else:
            raise TypeError(f"The type of metrics should be `list[fastNLP.MetricBase]` or `fastNLP.MetricBase`, "
                            f"got {type(metrics)}.")
    return _metrics


def accuracy_topk(y_true, y_prob, k=1):
    """Compute accuracy of y_true matching top-k probable labels in y_prob.

    :param y_true: ndarray, true label, [n_samples]
    :param y_prob: ndarray, label probabilities, [n_samples, n_classes]
    :param k: int, k in top-k
    :returns acc: accuracy of top-k

    """
    y_pred_topk = np.argsort(y_prob, axis=-1)[:, -1:-k - 1:-1]
    y_true_tile = np.tile(np.expand_dims(y_true, axis=1), (1, k))
    y_match = np.any(y_pred_topk == y_true_tile, axis=-1)
    acc = np.sum(y_match) / y_match.shape[0]
    return acc


def pred_topk(y_prob, k=1):
    """Return top-k predicted labels and corresponding probabilities.

    :param y_prob: ndarray, size [n_samples, n_classes], probabilities on labels
    :param k: int, k of top-k
    :returns (y_pred_topk, y_prob_topk):
        y_pred_topk: ndarray, size [n_samples, k], predicted top-k labels
        y_prob_topk: ndarray, size [n_samples, k], probabilities for top-k labels

    """
    y_pred_topk = np.argsort(y_prob, axis=-1)[:, -1:-k - 1:-1]
    x_axis_index = np.tile(
        np.arange(len(y_prob))[:, np.newaxis],
        (1, k))
    y_prob_topk = y_prob[x_axis_index, y_pred_topk]
    return y_pred_topk, y_prob_topk


class SQuADMetric(MetricBase):

    def __init__(self, pred_start=None, pred_end=None, target_start=None, target_end=None,
                 beta=1, right_open=False, print_predict_stat=False):
        """
        :param pred_start: [batch], 预测答案开始的index, 如果SQuAD2.0中答案为空则为0
        :param pred_end: [batch], 预测答案结束的index, 如果SQuAD2.0中答案为空则为0（左闭右闭区间）或者1（左闭右开区间）
        :param target_start: [batch], 正确答案开始的index, 如果SQuAD2.0中答案为空则为0
        :param target_end: [batch], 正确答案结束的index, 如果SQuAD2.0中答案为空则为0（左闭右闭区间）或者1（左闭右开区间）
        :param beta: float. f_beta分数，f_beta = (1 + beta^2)*(pre*rec)/(beta^2*pre + rec). 常用为beta=0.5, 1, 2. 若为0.5
            则精确率的权重高于召回率；若为1，则两者平等；若为2，则召回率权重高于精确率。
        :param right_open: boolean. right_open为true表示start跟end指针指向一个左闭右开区间，为false表示指向一个左闭右闭区间。
        :param print_predict_stat: boolean. True则输出预测答案是否为空与正确答案是否为空的统计信息, False则不输出
        """
        super(SQuADMetric, self).__init__()

        self._init_param_map(pred_start=pred_start, pred_end=pred_end, target_start=target_start, target_end=target_end)

        self.print_predict_stat = print_predict_stat

        self.no_ans_correct = 0
        self.no_ans_wrong = 0

        self.has_ans_correct = 0
        self.has_ans_wrong = 0

        self.has_ans_f = 0.

        self.no2no = 0
        self.no2yes = 0
        self.yes2no = 0
        self.yes2yes = 0

        self.f_beta = beta

        self.right_open = right_open

    def evaluate(self, pred_start, pred_end, target_start, target_end):
        """

        :param pred_start: [batch, seq_len]
        :param pred_end: [batch, seq_len]
        :param target_start: [batch]
        :param target_end: [batch]
        :param labels: [batch]
        :return:
        """
        start_inference = pred_start.max(dim=-1)[1].cpu().tolist()
        end_inference = pred_end.max(dim=-1)[1].cpu().tolist()
        start, end = [], []
        max_len = pred_start.size(1)
        t_start = target_start.cpu().tolist()
        t_end = target_end.cpu().tolist()

        for s, e in zip(start_inference, end_inference):
            start.append(min(s, e))
            end.append(max(s, e))
        for s, e, ts, te in zip(start, end, t_start, t_end):
            if not self.right_open:
                e += 1
                te += 1
            if ts == 0 and te == int(not self.right_open):
                if s == 0 and e == int(not self.right_open):
                    self.no_ans_correct += 1
                    self.no2no += 1
                else:
                    self.no_ans_wrong += 1
                    self.no2yes += 1
            else:
                if s == 0 and e == int(not self.right_open):
                    self.yes2no += 1
                else:
                    self.yes2yes += 1

                if s == ts and e == te:
                    self.has_ans_correct += 1
                else:
                    self.has_ans_wrong += 1
                a = [0] * s + [1] * (e - s) + [0] * (max_len - e)
                b = [0] * ts + [1] * (te - ts) + [0] * (max_len - te)
                a, b = torch.tensor(a), torch.tensor(b)

                TP = int(torch.sum(a * b))
                pre = TP / int(torch.sum(a)) if int(torch.sum(a)) > 0 else 0
                rec = TP / int(torch.sum(b)) if int(torch.sum(b)) > 0 else 0

                if pre + rec > 0:
                    f = (1 + (self.f_beta**2)) * pre * rec / ((self.f_beta**2) * pre + rec)
                else:
                    f = 0
                self.has_ans_f += f

    def get_metric(self, reset=True):
        evaluate_result = {}

        if self.no_ans_correct + self.no_ans_wrong + self.has_ans_correct + self.no_ans_wrong <= 0:
            return evaluate_result

        evaluate_result['EM'] = 0
        evaluate_result[f'f_{self.f_beta}'] = 0

        flag = 0

        if self.no_ans_correct + self.no_ans_wrong > 0:
            evaluate_result[f'noAns-f_{self.f_beta}'] = \
                round(100 * self.no_ans_correct / (self.no_ans_correct + self.no_ans_wrong), 3)
            evaluate_result['noAns-EM'] = \
                round(100 * self.no_ans_correct / (self.no_ans_correct + self.no_ans_wrong), 3)
            evaluate_result[f'f_{self.f_beta}'] += evaluate_result[f'noAns-f_{self.f_beta}']
            evaluate_result['EM'] += evaluate_result['noAns-EM']
            flag += 1

        if self.has_ans_correct + self.has_ans_wrong > 0:
            evaluate_result[f'hasAns-f_{self.f_beta}'] = \
                round(100 * self.has_ans_f / (self.has_ans_correct + self.has_ans_wrong), 3)
            evaluate_result['hasAns-EM'] = \
                round(100 * self.has_ans_correct / (self.has_ans_correct + self.has_ans_wrong), 3)
            evaluate_result[f'f_{self.f_beta}'] += evaluate_result[f'hasAns-f_{self.f_beta}']
            evaluate_result['EM'] += evaluate_result['hasAns-EM']
            flag += 1

        if self.print_predict_stat:
            evaluate_result['no2no'] = self.no2no
            evaluate_result['no2yes'] = self.no2yes
            evaluate_result['yes2no'] = self.yes2no
            evaluate_result['yes2yes'] = self.yes2yes

        if flag <= 0:
            return evaluate_result

        evaluate_result[f'f_{self.f_beta}'] = round(evaluate_result[f'f_{self.f_beta}'] / flag, 3)
        evaluate_result['EM'] = round(evaluate_result['EM'] / flag, 3)

        if reset:
            self.no_ans_correct = 0
            self.no_ans_wrong = 0

            self.has_ans_correct = 0
            self.has_ans_wrong = 0

            self.has_ans_f = 0.

            self.no2no = 0
            self.no2yes = 0
            self.yes2no = 0
            self.yes2yes = 0

        return evaluate_result

