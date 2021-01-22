import sys

sys.path.append("..")

from fastNLP.loader.config_loader import ConfigLoader, ConfigSection
from fastNLP.core.trainer import SeqLabelTrainer
from fastNLP.loader.dataset_loader import POSDatasetLoader, BaseLoader
from fastNLP.core.preprocess import SeqLabelPreprocess, load_pickle
from fastNLP.saver.model_saver import ModelSaver
from fastNLP.loader.model_loader import ModelLoader
from fastNLP.core.tester import SeqLabelTester
from fastNLP.models.sequence_modeling import SeqLabeling
from fastNLP.core.predictor import SeqLabelInfer

data_name = "people.txt"
data_path = "data_for_tests/people.txt"
pickle_path = "seq_label/"
data_infer_path = "data_for_tests/people_infer.txt"


def infer():
    # Load infer configuration, the same as test
    test_args = ConfigSection()
    ConfigLoader("config.cfg", "").load_config("./data_for_tests/config", {"POS_test": test_args})

    # fetch dictionary size and number of labels from pickle files
    word2index = load_pickle(pickle_path, "word2id.pkl")
    test_args["vocab_size"] = len(word2index)
    index2label = load_pickle(pickle_path, "id2class.pkl")
    test_args["num_classes"] = len(index2label)

    # Define the same model
    model = SeqLabeling(test_args)

    # Dump trained parameters into the model
    ModelLoader.load_pytorch(model, pickle_path + "saved_model.pkl")
    print("model loaded!")

    # Data Loader
    raw_data_loader = BaseLoader(data_name, data_infer_path)
    infer_data = raw_data_loader.load_lines()

    # Inference interface
    infer = SeqLabelInfer(pickle_path)
    results = infer.predict(model, infer_data)

    for res in results:
        print(res)
    print("Inference finished!")


def train_and_test():
    # Config Loader
    train_args = ConfigSection()
    ConfigLoader("config.cfg", "").load_config("./data_for_tests/config", {"POS": train_args})

    # Data Loader
    pos_loader = POSDatasetLoader(data_name, data_path)
    train_data = pos_loader.load_lines()

    # Preprocessor
    p = SeqLabelPreprocess()
    data_train, data_dev = p.run(train_data, pickle_path=pickle_path, train_dev_split=0.5)
    train_args["vocab_size"] = p.vocab_size
    train_args["num_classes"] = p.num_classes

    # Trainer
    trainer = SeqLabelTrainer(train_args)

    # Model
    model = SeqLabeling(train_args)

    # Start training
    trainer.train(model, data_train, data_dev)
    print("Training finished!")

    # Saver
    saver = ModelSaver(pickle_path + "saved_model.pkl")
    saver.save_pytorch(model)
    print("Model saved!")

    del model, trainer, pos_loader

    # Define the same model
    model = SeqLabeling(train_args)

    # Dump trained parameters into the model
    ModelLoader.load_pytorch(model, pickle_path + "saved_model.pkl")
    print("model loaded!")

    # Load test configuration
    test_args = ConfigSection()
    ConfigLoader("config.cfg", "").load_config("./data_for_tests/config", {"POS_test": test_args})

    # Tester
    tester = SeqLabelTester(test_args)

    # Start testing with validation data
    tester.test(model, data_dev)

    # print test results
    print(tester.show_matrices())
    print("model tested!")


if __name__ == "__main__":
    train_and_test()
    # infer()
