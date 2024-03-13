"""
Tscherepanow, M. (2010).
TopoART: A Topology Learning Hierarchical ART Network.
In K. Diamantaras, W. Duch, & L. S. Iliadis (Eds.),
Artificial Neural Networks – ICANN 2010 (pp. 157–167).
Berlin, Heidelberg: Springer Berlin Heidelberg.
doi:10.1007/978-3-642-15825-4_21.

"""

import numpy as np
from typing import Optional, Callable
from common.BaseART import BaseART


class TopoART(BaseART):

    def __init__(self, base_module: BaseART, betta_lower: float, tau: int, phi: int):
        params = dict(base_module.params, **{"beta_lower": betta_lower, "tau": tau, "phi": phi})
        super().__init__(params)
        self.base_module = base_module
        self.adjacency = np.zeros([], dtype=int)
        self._counter = np.zeros([], dtype=int)
        self._permanent_mask = np.zeros([], dtype=bool)

    @staticmethod
    def validate_params(params: dict):
        """
        validate clustering parameters

        Parameters:
        - params: dict containing parameters for the algorithm

        """
        assert "beta" in params, "TopoART is only compatible with ART modules relying on 'beta' for learning."
        assert "beta_lower" in params
        assert "tau" in params
        assert "phi" in params
        assert params["beta"] >= params["beta_lower"]
        assert params["phi"] <= params["tau"]

    @property
    def W(self):
        return self.base_module.W

    @W.setter
    def W(self, new_W: list[np.ndarray]):
        self.base_module.W = new_W

    def validate_data(self, X: np.ndarray):
        """
        validates the data prior to clustering

        Parameters:
        - X: data set

        """
        self.base_module.validate_data(X)

    def category_choice(self, i: np.ndarray, w: np.ndarray, params: dict) -> tuple[float, Optional[dict]]:
        """
        get the activation of the cluster

        Parameters:
        - i: data sample
        - w: cluster weight / info
        - params: dict containing parameters for the algorithm

        Returns:
            cluster activation, cache used for later processing

        """
        return self.base_module.category_choice(i, w, params)

    def match_criterion(self, i: np.ndarray, w: np.ndarray, params: dict, cache: Optional[dict] = None) -> tuple[float, dict]:
        """
        get the match criterion of the cluster

        Parameters:
        - i: data sample
        - w: cluster weight / info
        - params: dict containing parameters for the algorithm
        - cache: dict containing values cached from previous calculations

        Returns:
            cluster match criterion, cache used for later processing

        """
        return self.base_module.match_criterion(i, w, params, cache)

    def match_criterion_bin(self, i: np.ndarray, w: np.ndarray, params: dict, cache: Optional[dict] = None) -> tuple[bool, dict]:
        """
        get the binary match criterion of the cluster

        Parameters:
        - i: data sample
        - w: cluster weight / info
        - params: dict containing parameters for the algorithm
        - cache: dict containing values cached from previous calculations

        Returns:
            cluster match criterion binary, cache used for later processing

        """
        return self.base_module.match_criterion_bin(i, w, params, cache)

    def update(self, i: np.ndarray, w: np.ndarray, params: dict, cache: Optional[dict] = None) -> np.ndarray:
        """
        get the updated cluster weight

        Parameters:
        - i: data sample
        - w: cluster weight / info
        - params: dict containing parameters for the algorithm
        - cache: dict containing values cached from previous calculations

        Returns:
            updated cluster weight, cache used for later processing

        """
        if cache.get("resonant_c", -1) >= 0:
            self.adjacency[cache["resonant_c"], cache["current_c"]] += 1
        return self.base_module.update(i, w, params, cache)

    def new_weight(self, i: np.ndarray, params: dict) -> np.ndarray:
        """
        generate a new cluster weight

        Parameters:
        - i: data sample
        - w: cluster weight / info
        - params: dict containing parameters for the algorithm

        Returns:
            updated cluster weight

        """
        self.adjacency = np.pad(self.adjacency, ((0, 1), (0, 1)), "constant")
        self._counter = np.pad(self._counter, (0, 1), "constant", constant_values=(1,))
        self._permanent_mask = np.pad(self._permanent_mask, (0, 1), "constant")
        return self.new_weight(i, params)


    def prune(self, X: np.ndarray):
        self._permanent_mask += (self._counter >= self.params["phi"])
        perm_labels = np.where(self._permanent_mask)[0]
        self.W = [w for w, pm in zip(self.W, self._permanent_mask) if pm]
        self._counter = self._counter[perm_labels]

        label_map = {
            label: np.where(perm_labels == label)[0][0]
            for label in np.unique(self.labels_)
            if label in perm_labels
        }

        for i, x in enumerate(X):
            if self.labels_[i] in label_map:
                self.labels_[i] = label_map[self.labels_[i]]
            else:
                T_values, T_cache = zip(*[self.category_choice(x, w, params=self.params) for w in self.W])
                T = np.array(T_values)
                new_label = np.argmax(T)
                self.labels_[i] = new_label
                self._counter[new_label] += 1

    def step_prune(self, X: np.ndarray):
        sum_counter = sum(self._counter)
        if sum_counter > 0 and sum_counter % self.params["tau"] == 0:
            self.prune(X)

    def step_fit(self, x: np.ndarray, match_reset_func: Optional[Callable] = None) -> int:
        """
        fit the model to a single sample

        Parameters:
        - x: data sample
        - match_reset_func: a callable accepting the data sample, a cluster weight, the params dict, and the cache dict
            Permits external factors to influence cluster creation.
            Returns True if the cluster is valid for the sample, False otherwise

        Returns:
            cluster label of the input sample

        """
        resonant_c: int = -1

        if len(self.W) == 0:
            new_w = self.new_weight(x, self.params)
            self.add_weight(new_w)
            self.adjacency = np.zeros((1, 1), dtype=int)
            self._counter = np.ones((1, ), dtype=int)
            self._permanent_mask = np.zeros((1, ), dtype=bool)
            return 0
        else:
            T_values, T_cache = zip(*[self.category_choice(x, w, params=self.params) for w in self.W])
            T = np.array(T_values)
            while any(T > 0):
                c_ = int(np.argmax(T))
                w = self.W[c_]
                cache = T_cache[c_]
                m, cache = self.match_criterion_bin(x, w, params=self.params, cache=cache)
                no_match_reset = (
                        match_reset_func is None or
                        match_reset_func(x, w, c_, params=self.params, cache=cache)
                )
                if m and no_match_reset:
                    if resonant_c < 0:
                        params = self.params
                    else:
                        params = dict(self.params, **{"beta": self.params["beta_lower"]})
                    #TODO: make compatible with DualVigilanceART
                    new_w = self.update(
                        x,
                        w,
                        params=params,
                        cache=dict(cache, **{"resonant_c": resonant_c, "current_c": c_})
                    )
                    self.set_weight(c_, new_w)
                    if resonant_c < 0:
                        resonant_c = c_
                    else:
                        return resonant_c
                else:
                    T[c_] = -1

            if resonant_c < 0:
                c_new = len(self.W)
                w_new = self.new_weight(x, self.params)
                self.add_weight(w_new)
                return c_new

            return resonant_c


    def fit(self, X: np.ndarray, match_reset_func: Optional[Callable] = None, max_iter=1):
        """
        Fit the model to the data

        Parameters:
        - X: data set
        - match_reset_func: a callable accepting the data sample, a cluster weight, the params dict, and the cache dict
            Permits external factors to influence cluster creation.
            Returns True if the cluster is valid for the sample, False otherwise
        - max_iter: number of iterations to fit the model on the same data set

        """
        self.validate_data(X)
        self.check_dimensions(X)

        self.W: list[np.ndarray] = []
        self.labels_ = np.zeros((X.shape[0], ), dtype=int)
        for _ in range(max_iter):
            for i, x in enumerate(X):
                self.step_prune(X)
                c = self.step_fit(x, match_reset_func=match_reset_func)
                self.labels_[i] = c
        return self
