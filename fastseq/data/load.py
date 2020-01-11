# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/03_data.load.ipynb (unless otherwise specified).

__all__ = ['TSTensorSeq', 'TSTensorSeqy', 'TSDataLoader', 'TSBlock', 'TSDataBunch']

# Cell
from ..core import *
from .external import *
from fastcore.utils import *
from fastcore.imports import *
from fastai2.basics import *
from fastai2.tabular.core import *
from .transforms import *

# Cell
import numpy as np
import pandas as pd
from torch.utils.data import Dataset, DataLoader

# Cell
class TSTensorSeq(TensorSeq): pass
class TSTensorSeqy(TensorSeq):

    @classmethod
    def create(cls, t)->None:
        "Convert an array or a list of points `t` to a `Tensor`"
        return cls(tensor(t).view(-1, 1).float())

    def show(self, ctx=None, **kwargs):
        if 'figsize' in kwargs:
            del kwargs['figsize']
        array = np.array(self.cpu())
        array = no_emp_dim(array)
        x_len = self._meta.get('x_len',0)
        m = self._meta.get('m','-*r')
        t = np.arange(x_len,x_len+array.shape[1])[None,:]
        ctx.plot(t, array, m, **kwargs)
        return ctx

TSTensorSeqy.loss_func = MSELossFlat()

# Cell
# TODO maybe incl. start where the last one ended and therefor keep hidden state
@delegates()
class TSDataLoader(TfmdDL):
    def __init__(self, items, horizon, lookback=72, step=1, bs=64,  num_workers=0, after_batch=None, device=None,
                 after_item = None, **kwargs):
        self.items, self.horizon, self.lookback, self.step = items, horizon, lookback, step
        n = self.make_ids()
        after_batch = ifnone(after_batch, Cuda(device))
        after_item = ifnone(after_item, noop)
        super().__init__(dataset=items, bs=bs, num_workers=num_workers, after_batch=after_batch,
                         after_item=after_item, **kwargs)
        self.n = n

    def make_ids(self):
        # Slice each time series into examples, assigning IDs to each
        last_id = 0
        n_dropped = 0
        self._ids = {}
        for i, ts in enumerate(self.items):
            if isinstance(ts,tuple):
                ts = ts[0] # no idea why they become tuples
            num_examples = (ts.shape[-1] - self.lookback - self.horizon + self.step) // self.step
            # Time series shorter than the forecast horizon need to be dropped.
            if ts.shape[-1] < self.horizon:
                n_dropped += 1
                continue
            # For short time series zero pad the input
            if ts.shape[-1] < self.lookback + self.horizon:
                num_examples = 1
            for j in range(num_examples):
                self._ids[last_id + j] = (i, j * self.step)
            last_id += num_examples

            # Inform user about time series that were too short
        if n_dropped > 0:
            print("Dropped {}/{} time series due to length.".format(
                    n_dropped, len(self.items)))
        # Store the number of training examples
        return int(self._ids.__len__() )

    def get_id(self,idx):
        # Get time series
        ts_id, lookback_id = self._ids[idx]
        ts = self.items[ts_id]
        if isinstance(ts,tuple):
            ts = ts[0] # no idea why they become tuples
        # Prepare input and target. Zero pad if necessary.
        if ts.shape[-1] < self.lookback + self.horizon:
            # If the time series is too short, we zero pad
            x = ts[:, :-self.horizon]
            x = np.pad(
                x,
                pad_width=((0, 0), (self.lookback - x.shape[-1], 0)),
                mode='constant',
                constant_values=0
            )
            y = ts[:,-self.horizon:]
        else:
            x = ts[:,lookback_id:lookback_id + self.lookback]
            y = ts[:,lookback_id + self.lookback:lookback_id + self.lookback + self.horizon]
        return x, y

    def shuffle_fn(self, idxs):
        self.items.shuffle()
        return idxs

    def create_item(self, idx):
        if idx>=self.n: raise IndexError
        x, y = self.get_id(idx)
        return TSTensorSeq(x),TSTensorSeqy(y, x_len=x.shape[1], m='-*g')


# Cell

from fastai2.vision.data import *

@typedispatch
def show_batch(x: TensorSeq, y, samples, ctxs=None, max_n=10,rows=None, cols=None, figsize=None, **kwargs):
    if ctxs is None: ctxs = get_grid(min(len(samples), max_n), rows=rows, cols=cols, add_vert=1, figsize=figsize)
    ctxs = show_batch[object](x, y, samples=samples, ctxs=ctxs, max_n=max_n, **kwargs)
    return ctxs


# Cell
def TSBlock():
    return TransformBlock(dl_type=TSDataLoader,)

# Cell
class TSDataBunch(DataBunch):
    @classmethod
    @delegates(DataBunch.__init__)
    def from_folder(cls, path, valid_pct=.2, seed=None, horizon=None, lookback=None, step=1, nrows=None, skiprows=None, device=None, **kwargs):
        """Create from M-compition style in `path` with `train`,`test` csv-files.

        The `DataLoader` for the test set will be save as an attribute under `test_dl`
        """
        train, test = get_ts_files(path, nrows=nrows, skiprows=skiprows)
        horizon = ifnone(horizon, len(test[0]))
        lookback = ifnone(lookback, horizon * 3)
        step = step
        test = concat_ts_list(train, test, lookback)
        train, valid = sep_last(train, valid_pct)
        items = L(*train,*valid,*test)
        splits = IndexsSplitter(len(train),len(train)+len(valid), True)(items)
        dsrc = DataSource(items, noop, splits=splits, dl_type=TSDataLoader)
        db = dsrc.databunch(horizon=horizon, lookback=lookback, step=step, device=device, **kwargs)
        db.test_dl = TSDataLoader(test, horizon=horizon, lookback=lookback, step=step, device=device)
#         TODO add with test_dl, currently give buges I guess
        return db
