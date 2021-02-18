import argparse
import os

from fastNLP.core.optimizer import Optimizer
from fastNLP.core.preprocess import SeqLabelPreprocess
from fastNLP.core.tester import SeqLabelTester
from fastNLP.core.trainer import SeqLabelTrainer
from fastNLP.loader.config_loader import ConfigLoader, ConfigSection
from fastNLP.loader.dataset_loader import POSDatasetLoader
from fastNLP.loader.model_loader import ModelLoader
from fastNLP.models.sequence_modeling import SeqLabeling
from fastNLP.saver.model_saver import ModelSaver

parser = argparse.ArgumentParser()
parser.add_argument("-s", "--save", type=str, default="./seq_label/", help="path to save pickle files")
parser.add_argument("-t", "--train", type=str, default="../data_for_tests/people.txt",
                    help="path to the training data")
parser.add_argument("-c", "--config", type=str, default="../data_for_tests/config", help="path to the config file")
parser.add_argument("-m", "--model_name", type=str, default="seq_label_model.pkl", help="the name of the model")
parser.add_argument("-i", "--infer", type=str, default="../data_for_tests/people_infer.txt",
                    help="data used for inference")

args = parser.parse_args()
pickle_path = args.save
model_name = args.model_name
config_dir = args.config
data_path = args.train
data_infer_path = args.infer


def test_training():
    # Config Loader
    trainer_args = ConfigSection()
    model_args = ConfigSection()
    ConfigLoader("config.cfg").load_config(config_dir, {
        "test_seq_label_trainer": trainer_args, "test_seq_label_model": model_args})

    # Data Loader
    pos_loader = POSDatasetLoader(data_path)
    train_data = pos_loader.load_lines()

    # Preprocessor
    p = SeqLabelPreprocess()
    data_train, data_dev = p.run(train_data, pickle_path=pickle_path, train_dev_split=0.5)
    model_args["vocab_size"] = p.vocab_size
    model_args["num_classes"] = p.num_classes

    trainer = SeqLabelTrainer(
        epochs=trainer_args["epochs"],
        batch_size=trainer_args["batch_size"],
        validate=False,
        use_cuda=False,
        pickle_path=pickle_path,
        save_best_dev=trainer_args["save_best_dev"],
        model_name=model_name,
        optimizer=Optimizer("SGD", lr=0.01, momentum=0.9),
    )

    # Model
    model = SeqLabeling(model_args)

    # Start training
    trainer.train(model, data_train, data_dev)

    # Saver
    saver = ModelSaver(os.path.join(pickle_path, model_name))
    saver.save_pytorch(model)

    del model, trainer, pos_loader

    # Define the same model
    model = SeqLabeling(model_args)

    # Dump trained parameters into the model
    ModelLoader.load_pytorch(model, os.path.join(pickle_path, model_name))

    # Load test configuration
    tester_args = ConfigSection()
    ConfigLoader("config.cfg").load_config(config_dir, {"test_seq_label_tester": tester_args})

    # Tester
    tester = SeqLabelTester(save_output=False,
                            save_loss=True,
                            save_best_dev=False,
                            batch_size=4,
                            use_cuda=False,
                            pickle_path=pickle_path,
                            model_name="seq_label_in_test.pkl",
                            print_every_step=1
                            )

    # Start testing with validation data
    tester.test(model, data_dev)

    loss, accuracy = tester.metrics
    assert 0 < accuracy < 1
