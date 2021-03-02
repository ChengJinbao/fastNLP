import torch


class Field(object):
    """A field defines a data type.

    """

    def __init__(self, is_target: bool):
        self.is_target = is_target

    def index(self, vocab):
        raise NotImplementedError

    def get_length(self):
        raise NotImplementedError

    def to_tensor(self, padding_length):
        raise NotImplementedError


class TextField(Field):
    def __init__(self, text, is_target):
        """
        :param text: list of strings
        :param is_target: bool
        """
        super(TextField, self).__init__(is_target)
        self.text = text
        self._index = None

    def index(self, vocab):
        if self._index is None:
            self._index = [vocab[c] for c in self.text]
        else:
            raise RuntimeError("Replicate indexing of this field.")
        return self._index

    def get_length(self):
        """Fetch the length of the text field.

        :return length: int, the length of the text.

        """
        return len(self.text)

    def to_tensor(self, padding_length: int):
        """Convert text field to tensor.

        :param padding_length: int
        :return tensor: torch.LongTensor, of shape [padding_length, ]
        """
        pads = []
        if self._index is None:
            raise RuntimeError("Indexing not done before to_tensor in TextField.")
        if padding_length > self.get_length():
            pads = [0] * (padding_length - self.get_length())
        return torch.LongTensor(self._index + pads)


class LabelField(Field):
    """The Field representing a single label. Can be a string or integer.

    """
    def __init__(self, label, is_target=True):
        super(LabelField, self).__init__(is_target)
        self.label = label
        self._index = None

    def get_length(self):
        """Fetch the length of the label field.

        :return length: int, the length of the label, always 1.
        """
        return 1

    def index(self, vocab):
        if self._index is None:
            if isinstance(self.label, str):
                self._index = vocab[self.label]
        return self._index

    def to_tensor(self, padding_length):
        if self._index is None:
            if isinstance(self.label, int):
                return torch.tensor(self.label)
            elif isinstance(self.label, str):
                raise RuntimeError("Field {} not indexed. Call index method.".format(self.label))
            else:
                raise RuntimeError(
                    "Not support type for LabelField. Expect str or int, got {}.".format(type(self.label)))
        else:
            return torch.LongTensor([self._index])


if __name__ == "__main__":
    tf = TextField("test the code".split(), is_target=False)
