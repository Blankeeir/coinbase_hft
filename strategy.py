"""Channel‑breakout strategy enhanced with real‑time OBI features."""
import numpy as np
from sklearn.linear_model import SGDClassifier
from collections import deque
import datetime as dt

class BreakoutWithOBI:
    def __init__(self, book, window=120, obi_thr=0.15):
        self.book = book
        self.window = window
        self.obi_thr = obi_thr
        self.x_hist = deque(maxlen=5000)
        self.y_hist = deque(maxlen=5000)
        self.model = SGDClassifier(loss='log', random_state=42)
        self._warm = False

    def _features(self):
        obi = self.book.obi()
        mid = self.book.mid_price()
        return np.array([obi, mid])

    def _label(self):
        c_high, c_low = self.book.channel()
        mid = self.book.mid_price()
        if c_high is None:
            return 0
        if mid > c_high:
            return 1
        elif mid < c_low:
            return -1
        return 0

    def on_tick(self, now:dt.datetime):
        x = self._features()
        y = self._label()
        if y != 0:
            self.x_hist.append(x)
            self.y_hist.append(1 if y == 1 else 0)   # binary: up vs not‑up
            if len(self.x_hist) > 100 and not self._warm:
                self.model.partial_fit(np.vstack(self.x_hist), np.array(self.y_hist), classes=[0,1])
                self._warm = True
        if not self._warm:
            return None   # still warming
        prob_up = self.model.predict_proba(x.reshape(1,-1))[0][1]
        obi = x[0]
        if prob_up > 0.5 and obi > self.obi_thr:
            return 'BUY'
        if prob_up < 0.5 and obi < -self.obi_thr:
            return 'SELL'
        return None
