import copy
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
print(sys.path)
import torch

from fastNLP.core.dataset import DataSet
from fastNLP.api.pipeline import Pipeline
from fastNLP.api.processor import VocabProcessor, IndexerProcessor, SeqLenProcessor, ModelProcessor, Index2WordProcessor
from fastNLP.core.instance import Instance
from fastNLP.core.metrics import SeqLabelEvaluator
from fastNLP.core.optimizer import Optimizer
from fastNLP.core.trainer import Trainer
from fastNLP.io.config_loader import ConfigLoader, ConfigSection
from fastNLP.io.dataset_loader import PeopleDailyCorpusLoader
from fastNLP.models.sequence_modeling import AdvSeqLabel


cfgfile = './pos_tag.cfg'
datadir = "/home/zyfeng/data/"
data_name = "CWS_POS_TAG_NER_people_daily.txt"
# datadir = "/home/zyfeng/env/fastnlp_v_2/test/data_for_tests"
# data_name = "people_daily_raw.txt"


pos_tag_data_path = os.path.join(datadir, data_name)
pickle_path = "save"
data_infer_path = os.path.join(datadir, "infer.utf8")


def train():
    # load config
    train_param = ConfigSection()
    model_param = ConfigSection()
    ConfigLoader().load_config(cfgfile, {"train": train_param, "model": model_param})
    print("config loaded")

    # Data Loader
    loader = PeopleDailyCorpusLoader()
    train_data, _ = loader.load(os.path.join(datadir, data_name))
    print("data loaded")

    dataset = DataSet()
    for data in train_data:
        instance = Instance()
        instance["words"] = data[0]
        instance["tag"] = data[1]
        dataset.append(instance)
    print("dataset transformed")

    # processor_1 = FullSpaceToHalfSpaceProcessor('words')
    # processor_1(dataset)
    word_vocab_proc = VocabProcessor('words')
    tag_vocab_proc = VocabProcessor("tag")
    word_vocab_proc(dataset)
    tag_vocab_proc(dataset)
    word_indexer = IndexerProcessor(word_vocab_proc.get_vocab(), 'words', 'word_seq', delete_old_field=True)
    word_indexer(dataset)
    tag_indexer = IndexerProcessor(tag_vocab_proc.get_vocab(), 'tag', 'truth', delete_old_field=True)
    tag_indexer(dataset)
    seq_len_proc = SeqLenProcessor("word_seq", "word_seq_origin_len")
    seq_len_proc(dataset)
    #torch.save(dataset, "data_set.pkl")

    dev_set = copy.deepcopy(dataset)
    dev_set.set_is_target(truth=True)

    print("processors defined")
    # dataset.set_is_target(tag_ids=True)
    model_param["vocab_size"] = len(word_vocab_proc.get_vocab())
    model_param["num_classes"] = len(tag_vocab_proc.get_vocab())
    print("vocab_size={}  num_classes={}".format(len(word_vocab_proc.get_vocab()), len(tag_vocab_proc.get_vocab())))

    # define a model
    model = AdvSeqLabel(model_param)

    # call trainer to train
    trainer = Trainer(epochs=train_param["epochs"],
                      batch_size=train_param["batch_size"],
                      validate=True,
                      optimizer=Optimizer("Adam", lr=0.01, weight_decay=0.9),
                      evaluator=SeqLabelEvaluator(),
                      use_cuda=True
                      )
    trainer.train(model, dataset, dev_set)

    model_proc = ModelProcessor(model, "word_seq_origin_len")
    dataset.set_is_target(truth=True)
    res = model_proc.process(dataset)

    decoder = Index2WordProcessor(tag_vocab_proc.get_vocab(), "predict", "outputs")

    # save model & pipeline
    pp = Pipeline([word_indexer, seq_len_proc, model_proc, decoder])
    save_dict = {"pipeline": pp}
    torch.save(save_dict, "model_pp.pkl")


def test():
    pass


def infer():
    pass


if __name__ == "__main__":
    train()
    """
    import argparse

    parser = argparse.ArgumentParser(description='Run a chinese word segmentation model')
    parser.add_argument('--mode', help='set the model\'s model', choices=['train', 'test', 'infer'])
    args = parser.parse_args()
    if args.mode == 'train':
        train()
    elif args.mode == 'test':
        test()
    elif args.mode == 'infer':
        infer()
    else:
        print('no mode specified for model!')
        parser.print_help()

"""
