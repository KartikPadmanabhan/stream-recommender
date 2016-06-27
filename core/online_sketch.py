from .base import Base

import numpy as np
import numpy.linalg as ln
import scipy.sparse as sp
from sklearn import preprocessing
from sklearn.utils.extmath import safe_sparse_dot


class OnlineSketch(Base):

    """Inspired by: Streaming Anomaly Detection using Online Matrix Sketching
    """

    def __init__(self, contexts):

        self.contexts = contexts
        self.p = np.sum(list(contexts.values()))

        self.k = 40  # dimension of projected vectors
        self.ell = int(np.sqrt(self.k))

        self._Base__clear()

    def _Base__clear(self):
        self.n_user = 0
        self.users = {}

        self.n_item = 0
        self.items = {}

        self.i_mat = sp.csr_matrix([])

        self.B = np.zeros((self.k, self.ell))

        # random projection matrix
        self.R = np.random.normal(0., 1 / self.k, (self.k, self.p))

    def _Base__check(self, d):

        u_index = d['u_index']
        if u_index not in self.users:
            self.users[u_index] = {'observed': set()}
            self.n_user += 1
            self.p += 1

            # projection matrix: insert a new column for new user ID
            col = np.random.normal(0., 1 / self.k, (self.k, 1))
            offset = self.n_user - 1
            self.R = np.concatenate((self.R[:, :offset], col, self.R[:, offset:]), axis=1)

        i_index = d['i_index']
        if i_index not in self.items:
            self.items[i_index] = {}
            self.n_item += 1
            self.p += 1

            i_vec = np.array([np.append(np.zeros(self.n_item), d['item'])]).T
            if self.i_mat.size == 0:
                self.i_mat = i_vec
            else:
                # item matrix: insert a new row for new item ID
                z = np.zeros((1, self.i_mat.shape[1]))
                self.i_mat = sp.csr_matrix(sp.vstack((self.i_mat[:(self.n_item - 1)],
                                                      z,
                                                      self.i_mat[(self.n_item - 1):])))
                self.i_mat = sp.csr_matrix(sp.hstack((self.i_mat, i_vec)))

            # projection matrix: insert a new column for new item ID
            col = np.random.normal(0., 1 / self.k, (self.k, 1))
            offset = self.n_user + self.contexts['user'] + self.contexts['others'] + self.n_item - 1
            self.R = np.concatenate((self.R[:, :offset], col, self.R[:, offset:]), axis=1)

    def _Base__update(self, d, is_batch_train=False):
        u = np.append(np.zeros(self.n_user), d['user'])
        u[d['u_index']] = 1.

        i = np.append(np.zeros(self.n_item), d['item'])
        i[d['i_index']] = 1.

        y = np.concatenate((u, d['others'], i))

        y = np.dot(self.R, y)  # random projection
        y = preprocessing.normalize(np.array([y]), norm='l2').flatten()

        # combine current sketched matrix with input at time t
        zero_cols = np.where(np.isclose(self.B, 0).all(0) == 1)[0]
        j = zero_cols[0] if zero_cols.size != 0 else self.ell - 1  # left-most all-zero column in B
        self.B[:, j] = y

        U, s, V = ln.svd(self.B, full_matrices=False)

        # update ell orthogonal bases
        self.U = U[:, :self.ell]
        s = s[:self.ell]

        # shrink step in the Frequent Directions algorithm
        # (shrink singular values based on the squared smallest singular value)
        delta = s[-1] ** 2
        s = np.sqrt(s ** 2 - delta)

        self.B = np.dot(self.U, np.diag(s))

    def _Base__recommend(self, d, target_i_indices, at=10):
        # i_mat is (n_item_context, n_item) for all possible items
        # extract only target items
        i_mat = self.i_mat[:, target_i_indices]

        n_target = len(target_i_indices)

        # u_mat will be (n_user_context, n_item) for the target user
        u = np.concatenate((np.zeros(self.n_user), d['user'], d['others']))
        u[d['u_index']] = 1.
        u_vec = np.array([u]).T

        u_mat = sp.csr_matrix(np.repeat(u_vec, n_target, axis=1))

        # stack them into (p, n_item) matrix
        Y = sp.vstack((u_mat, i_mat))
        Y = safe_sparse_dot(self.R, Y)  # random projection -> dense output
        Y = sp.csr_matrix(preprocessing.normalize(Y, norm='l2', axis=0))

        X = np.identity(self.k) - np.dot(self.U, self.U.T)
        A = safe_sparse_dot(X, Y, dense_output=True)

        scores = ln.norm(A, axis=0, ord=2)

        return self._Base__scores2recos(scores, target_i_indices, at)
