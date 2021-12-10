import torch
from reproduction.coreference_resolution.model.config import Config
from reproduction.coreference_resolution.model.metric import CRMetric
from reproduction.coreference_resolution.data_load.cr_loader import CRLoader
from fastNLP import Tester
import argparse


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--path')
    args = parser.parse_args()
    
    cr_loader = CRLoader()
    config = Config()
    data_info = cr_loader.process({'train': config.train_path, 'dev': config.dev_path,
                                               'test': config.test_path})
    metirc = CRMetric()
    model = torch.load(args.path)
    tester = Tester(data_info.datasets['test'],model,metirc,batch_size=1,device="cuda:0")
    tester.test()
    print('test over')


