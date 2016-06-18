# coding: utf-8

from logging import getLogger, StreamHandler, DEBUG
logger = getLogger(__name__)
handler = StreamHandler()
handler.setLevel(DEBUG)
logger.setLevel(DEBUG)
logger.addHandler(handler)

import numpy as np

from core.incremental_MF import IncrementalMF
from core.incremental_FMs import IncrementalFMs
from core.online_sketch import OnlineSketch
from core.random import Random
from core.popular import Popular

from converter.converter import Converter


class Runner:

    def __init__(self, dataset='ML1M', window_size=5000, n_epoch=1):
        self.window_size = window_size

        # number of epochs for the batch training
        self.n_epoch = n_epoch

        # load dataset
        self.data = Converter().convert(dataset=dataset)

        logger.debug('[exp] %s | window_size = %d, n_epoch = %d' % (dataset, window_size, n_epoch))
        logger.debug('[exp] n_sample = %d; %d (20%%) + %d (10%%) + %d (70%%)' % (
            self.data.n_sample, self.data.n_batch_train, self.data.n_batch_test, self.data.n_test))
        logger.debug('[exp] n_user = %d, n_item = %d' % (self.data.n_user, self.data.n_item))

    def iMF(self, is_static=False):
        """Incremental Matrix Factorization

        Args:
            is_static (bool): choose whether a model is incrementally updated.
                True -- baseline
                False -- incremental matrix factorization

        Returns:
            list of float values: Simple Moving Averages (i.e. incremental recall).
            float: average time to recommend/update for one sample

        """
        if is_static:
            logger.debug('# static MF')
        else:
            logger.debug('# iMF')

        def create():
            return IncrementalMF(is_static)

        model, res = self.__run(create)
        return res

    def iFMs(self, is_context_aware=False, is_static=False):
        """Incremental Factorization Machines

        Args:
            is_context_aware (bool): Choose whether a feature vector incorporates contextual variables of the dataset.

        Returns:
            list of float values: Simple Moving Averages (i.e. incremental recall).
            float: average time to recommend/update for one sample

        """
        if is_static:
            logger.debug('# static FMs')
        else:
            logger.debug('# iFMs')

        def create():
            return IncrementalFMs(contexts=self.data.contexts, is_static=is_static)

        model, res = self.__run(create)

        logger.debug(
            'Regularization parameters: w0 = %s, w = %s, V = %s' % (
                model.l2_reg_w0,
                model.l2_reg_w,
                model.l2_reg_V))

        return res

    def sketch(self):
        """Online Matrix Sketching

        Returns:
            list of float values: Simple Moving Averages (i.e. incremental recall).
            float: average time to recommend/update for one sample

        """
        logger.debug('# matrix sketching')

        def create():
            return OnlineSketch(
                contexts=self.data.contexts)

        model, res = self.__run(create)

        return res

    def random(self):
        """Random baseline

        Returns:
            list of float values: Simple Moving Averages (i.e. incremental recall).
            float: average time to recommend/update for one sample

        """
        logger.debug('# random baseline')

        def create():
            return Random()

        model, res = self.__run(create)

        return res

    def popular(self):
        """Popularity (non-personalized) baseline

        Returns:
            list of float values: Simple Moving Averages (i.e. incremental recall).
            float: average time to recommend/update for one sample

        """
        logger.debug('# popularity baseline')

        def create():
            return Popular()

        model, res = self.__run(create)

        return res

    def __run(self, callback):
        """Test runner.

        Args:
            callback (function): Create a model used by this test run.

        Returns:
            instance of incremental model class: Created by the callback function.
            list of float values: Simple Moving Averages (i.e. incremental recall).
            float: average time to recommend/update for one sample

        """
        batch_tail = self.data.n_batch_train + self.data.n_batch_test

        model = callback()

        # pre-train
        # 20% for batch training | 10% for batch evaluate
        # after the batch training, 10% samples are used for incremental updating
        model.fit(
            self.data.samples[:self.data.n_batch_train],
            self.data.samples[self.data.n_batch_train:batch_tail],
            n_epoch=self.n_epoch
        )

        # 70% incremental evaluation and updating
        res = model.evaluate(self.data.samples[batch_tail:], window_size=self.window_size)

        return model, res


def save(path, recalls, avg_recommend, avg_update):
    with open(path, 'w') as f:
        f.write('\n'.join(map(str, np.append(np.array([avg_recommend, avg_update]), recalls))))

import click

models = ['static-MF', 'iMF', 'static-FMs', 'iFMs', 'sketch', 'random', 'popular']
datasets = ['ML1M', 'ML100k', 'LastFM']


@click.command()
@click.option('--model', type=click.Choice(models), default=models[0], help='Choose a factorization model')
@click.option('--dataset', type=click.Choice(datasets), default=datasets[0], help='Choose a dataset')
@click.option('--window_size', default=5000, help='Window size of the simple moving average for incremental evaluation.')
@click.option('--n_epoch', default=1, help='Number of epochs for batch training.')
@click.option('--n_trial', default=1, help='Number of trials under the same setting.')
def cli(model, dataset, window_size, n_epoch, n_trial):
    exp = Runner(dataset=dataset, window_size=window_size, n_epoch=n_epoch)

    for i in range(n_trial):
        if model == 'static-MF' or model == 'iMF':
            res = exp.iMF(is_static=True) if model == 'static-MF' else exp.iMF()
        elif model == 'sketch':
            res = exp.sketch()
        elif model == 'random':
            res = exp.random()
        elif model == 'popular':
            res = exp.popular()
        elif model == 'static-FMs' or model == 'iFMs':
            res = exp.iFMs(is_static=True) if model == 'static-FMs' else exp.iFMs()

        recalls, avg_recommend, avg_update = res
        save('results/%s_%s_%s_%s.txt' % (dataset, model, window_size, i + 1),
             recalls, avg_recommend, avg_update)

if __name__ == '__main__':
    cli()
