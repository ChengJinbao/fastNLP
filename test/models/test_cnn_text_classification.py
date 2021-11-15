
import unittest

from .model_runner import *
from fastNLP.models.cnn_text_classification import CNNText


class TestCNNText(unittest.TestCase):
    def test_case1(self):
        # 测试能否正常运行CNN
        init_emb = (VOCAB_SIZE, 30)
        model = CNNText(init_emb,
                        NUM_CLS,
                        kernel_nums=(1, 3, 5),
                        kernel_sizes=(1, 3, 5),
                        dropout=0.5)
        RUNNER.run_model_with_task(TEXT_CLS, model)
