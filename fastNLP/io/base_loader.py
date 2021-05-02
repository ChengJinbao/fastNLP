import _pickle as pickle
import os


class BaseLoader(object):

    def __init__(self):
        super(BaseLoader, self).__init__()

    @staticmethod
    def load_lines(data_path):
        with open(data_path, "r", encoding="utf=8") as f:
            text = f.readlines()
        return [line.strip() for line in text]

    @classmethod
    def load(cls, data_path):
        with open(data_path, "r", encoding="utf-8") as f:
            text = f.readlines()
        return [[word for word in sent.strip()] for sent in text]

    @classmethod
    def load_with_cache(cls, data_path, cache_path):
        if os.path.isfile(cache_path) and os.path.getmtime(data_path) < os.path.getmtime(cache_path):
            with open(cache_path, 'rb') as f:
                return pickle.load(f)
        else:
            obj = cls.load(data_path)
            with open(cache_path, 'wb') as f:
                pickle.dump(obj, f)
            return obj


class ToyLoader0(BaseLoader):
    """
        For CharLM
    """

    def __init__(self, data_path):
        super(ToyLoader0, self).__init__(data_path)

    def load(self):
        with open(self.data_path, 'r') as f:
            corpus = f.read().lower()
        import re
        corpus = re.sub(r"<unk>", "unk", corpus)
        return corpus.split()
