from fastNLP.envs.imports import _NEED_IMPORT_TORCH
if _NEED_IMPORT_TORCH:
    import torch
    from torch.nn import Module
    import torch.nn as nn
else:
    from fastNLP.core.utils.dummy_class import DummyClass as Module


# 1. 最为基础的分类模型
class TorchNormalModel_Classification_1(Module):
    """
    单独实现 train_step 和 evaluate_step；
    """
    def __init__(self, num_labels, feature_dimension):
        super(TorchNormalModel_Classification_1, self).__init__()
        self.num_labels = num_labels

        self.linear1 = nn.Linear(in_features=feature_dimension, out_features=10)
        self.ac1 = nn.ReLU()
        self.linear2 = nn.Linear(in_features=10, out_features=10)
        self.ac2 = nn.ReLU()
        self.output = nn.Linear(in_features=10, out_features=num_labels)
        self.loss_fn = nn.CrossEntropyLoss()

    def forward(self, x):
        x = self.ac1(self.linear1(x))
        x = self.ac2(self.linear2(x))
        x = self.output(x)
        return x

    def train_step(self, x, y):
        x = self(x)
        return {"loss": self.loss_fn(x, y)}

    def evaluate_step(self, x, y):
        """
        如果不加参数 y，那么应该在 trainer 中设置 output_mapping = {"y": "target"}；
        """

        x = self(x)
        x = torch.max(x, dim=-1)[1]
        return {"preds": x, "target": y}


class TorchNormalModel_Classification_2(Module):
    """
    只实现一个 forward 函数，来测试用户自己在外面初始化 DDP 的场景；
    """
    def __init__(self, num_labels, feature_dimension):
        super(TorchNormalModel_Classification_2, self).__init__()
        self.num_labels = num_labels

        self.linear1 = nn.Linear(in_features=feature_dimension, out_features=10)
        self.ac1 = nn.ReLU()
        self.linear2 = nn.Linear(in_features=10, out_features=10)
        self.ac2 = nn.ReLU()
        self.output = nn.Linear(in_features=10, out_features=num_labels)
        self.loss_fn = nn.CrossEntropyLoss()

    def forward(self, x, y):
        x = self.ac1(self.linear1(x))
        x = self.ac2(self.linear2(x))
        x = self.output(x)
        loss = self.loss_fn(x, y)
        x = torch.max(x, dim=-1)[1]
        return {"loss": loss, "preds": x, "target": y}


class TorchNormalModel_Classification_3(Module):
    """
    只实现一个 forward 函数，来测试用户自己在外面初始化 DDP 的场景；
    关闭 auto_param_call，forward 只有一个 batch 参数；
    """
    def __init__(self, num_labels, feature_dimension):
        super(TorchNormalModel_Classification_3, self).__init__()
        self.num_labels = num_labels

        self.linear1 = nn.Linear(in_features=feature_dimension, out_features=10)
        self.ac1 = nn.ReLU()
        self.linear2 = nn.Linear(in_features=10, out_features=10)
        self.ac2 = nn.ReLU()
        self.output = nn.Linear(in_features=10, out_features=num_labels)
        self.loss_fn = nn.CrossEntropyLoss()

    def forward(self, batch):
        x = batch["x"]
        y = batch["y"]
        x = self.ac1(self.linear1(x))
        x = self.ac2(self.linear2(x))
        x = self.output(x)
        loss = self.loss_fn(x, y)
        x = torch.max(x, dim=-1)[1]
        return {"loss": loss, "preds": x, "target": y}



