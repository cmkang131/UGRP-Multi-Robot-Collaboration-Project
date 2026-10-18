"""Stone Soup 1.7 global 1:1 assignment over own-RGB landmark hypotheses.

Upstream GNNWith2DAssignment is called directly, not reimplemented. Our
hypothesiser supplies the existing planar EKF innovation and per-observation
covariance (including wrapped line angles), without pose/map/identity truth.
"""
from datetime import datetime, timedelta
from importlib.metadata import version
import numpy as np

PROFILE = 'rovio_object_gnn_v1'


def assign(costs, states, covariances, t, gate):
    from stonesoup.base import Property
    from stonesoup.dataassociator.neighbour import GNNWith2DAssignment
    from stonesoup.hypothesiser.base import Hypothesiser
    from stonesoup.types.detection import Detection, MissedDetection
    from stonesoup.types.hypothesis import SingleDistanceHypothesis
    from stonesoup.types.multihypothesis import MultipleHypothesis
    from stonesoup.types.prediction import GaussianStatePrediction

    if version('stonesoup') != '1.7':
        raise ValueError('PINNED_STONESOUP_1_7_REQUIRED')
    costs = np.asarray(costs, float)
    if not costs.size: return {}
    stamp = datetime(2000, 1, 1) + timedelta(seconds=t)  # arbitrary epoch, SIM only
    predictions = [GaussianStatePrediction(z, p, timestamp=stamp)
                   for z, p in zip(states, covariances)]

    class OwnRGBHypothesiser(Hypothesiser):
        matrix: np.ndarray = Property()
        predicted: list = Property()
        miss_cost: float = Property()

        def hypothesise(self, track, detections, timestamp, **kwargs):
            prediction = self.predicted[track]
            hypotheses = [SingleDistanceHypothesis(prediction, MissedDetection(timestamp=timestamp), self.miss_cost)]
            for d in detections:
                distance = self.matrix[track, d.metadata['index']]
                if np.isfinite(distance) and distance <= self.miss_cost:
                    hypotheses.append(SingleDistanceHypothesis(prediction, d, float(distance)))
            return MultipleHypothesis(hypotheses)

    # Same chi-square(2)99% gate as the inherited observation EKF. Squared
    # Mahalanobis costs are valid distance hypotheses; missed cost equals gate.
    # The library's assignment algorithm and missed-detection handling stay intact.
    detections = [Detection([0., 0.], timestamp=stamp, metadata={'index': j})
                  for j in range(costs.shape[1])]
    hypotheses = GNNWith2DAssignment(OwnRGBHypothesiser(costs, predictions, gate)).associate(
        list(range(costs.shape[0])), detections, stamp)
    return {h.measurement.metadata['index']: i for i, h in hypotheses.items() if h}
