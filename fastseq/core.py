# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/00_core.ipynb (unless otherwise specified).

__all__ = ['TSeries', 'no_emp_dim', 'show_graph', 'test_graph_exists', 'show_graphs', 'TensorSeq', 'pad_zeros', 'Skip',
           'get_ts_files', 'concat_ts_list', 'sep_last', 'IndexsSplitter', 'ts_lists', 'ToElapsed', 'make_interval',
           'melted_ts_2_lists']

# Cell
from fastcore.all import *
from fastai2.basics import *
import pandas as pd
import numpy as np

# Cell
class TSeries(TensorBase):pass

# Cell

def no_emp_dim(x):
    if len(x.shape)==1 :
        x = x[None,:]
    return np.vstack(x)

def show_graph(array, ax=None, figsize=None, title=None, ctx=None, tx=None, **kwargs):
    "Show an array on `ax`."
    # Handle pytorch axis order
    if hasattrs(array, ('data','cpu','permute')):
        array = array.data.cpu()
    elif not isinstance(array,np.ndarray):
        array=array(array)
    arrays = no_emp_dim(array)
    ax = ifnone(ax,ctx)
    if figsize is None: figsize = (5,5)
    if ax is None: _,ax = plt.subplots(figsize=figsize)
    tx = ifnone(tx,np.arange(arrays[0].shape[0]))
    for a, c in zip(arrays, ['b', 'c', 'm', 'y', 'k',]):
        ax.plot(tx, a, '-*'+c, **kwargs)

    if title is not None: ax.set_title(title)
#     ax.axis('off')
    return ax

# Cell
def test_graph_exists(ax):
    "Test there is a graph displayed in `ax`"
    assert ax

# Cell
@delegates(subplots)
def show_graphs(arrays, rows=1, titles=None, **kwargs):
    "Show all images `arrays` as subplots with `rows` using `titles`"
    cols = int(math.ceil(len(arrays)/rows))
    if titles is None: titles = [None]*len(arrays)
    axs = subplots(rows,cols,**kwargs)[1].flat
    for a,t,ax in zip(arrays, titles, axs):
        show_graph(a, ax=ax, title=t)

# Cell
class TensorSeq(TensorBase):
    def show(self, ctx=None, **kwargs):
        return show_graph(self, ctx=ctx, **kwargs)

# Cell
def pad_zeros(X, lenght):
    return  np.pad(
                X,
                pad_width=((0, 0), (lenght - X.shape[-1], 0)),
                mode='constant',
                constant_values=0
            )

# Cell
def Skip(percentage_remove):
    """Helper function for `pd.read_csv` and will randomly not load `percentage_remove`% of the whole dataset """

    def skip(x):
        if (np.random.rand() < percentage_remove or x == 0):
            return False
        return True
    return skip

# Cell
# TODO skip will skip different rows for train and val

def get_ts_files(path, recurse=True, folders=None, **kwargs):
    "Get image files in `path` recursively, only in `folders`, if specified."
    items = []
    for f in get_files(path, extensions=['.csv'], recurse=recurse, folders=folders):
        df = pd.read_csv(f, **kwargs)
        items.append(ts_lists(df.iloc[:, 1:].values))
    return items

# Cell
def concat_ts_list(train, val, lookback = 72):
    items=L()
    assert len(train) == len(val)
    for t, v in zip(train, val):
        items.append(np.concatenate([t[:, -lookback:],v],1))
    return items

# Cell
def sep_last(items, pct = .2):
    train,valid=L(),L()
    for ts in items:
        split_idx = int((1-pct)*ts.shape[1])
        train.append(ts[:,:split_idx])
        valid.append(ts[:,split_idx:])
    return train, valid

# Cell
def IndexsSplitter(train_idx, val_idx=None, test=None):
    """Split `items` from 0 to `train_idx` in the training set, from `train_idx` to `val_idx` (or the end) in the validation set.

    Optionly if `test` will  in test set will also make test from val_idx to end.
    """
    _val_idx = ifnone(val_idx,-1)
    do_test = ifnone(test, False)
    def _inner(items, **kwargs):
        if _val_idx == -1:
            val_idx = len(items)
        else:
            val_idx = _val_idx
        train = L(np.arange(0, train_idx), use_list=True)
        valid = L(np.arange(train_idx, val_idx), use_list=True)
        if do_test:
            test = L(np.arange(val_idx,len(items)), use_list=True)
            return train, valid, test
        if not val_idx == len(items):
            warnings.warn("You lose data")
        return train, valid
    return _inner

# Cell
def ts_lists(ts:np.ndarray)-> L:
    """Transforms a `np.ndarray` of shape (timeseries, max_time) to a list of timeseries with shape (1,time).

    where:

    max_time = the length of the longest timeserie

    time = the length of the non-nan values of that specific timeserie
    """
    lst = L()
    for time_series in ts:
        lst.append(time_series[~np.isnan(time_series)][None,:])
    return lst

# Cell
class ToElapsed():
    changed = False
    def __call__(self, s):
        if pd.api.types.is_datetime64_any_dtype(s.dtype):
            self.changed = True
            return s.astype(np.int64) // 10 ** 9
        return s

    def decode(self, s):
        if self.changed:
            return pd.Series(pd.to_datetime(s *(10 ** 9)))
        return s


# Cell
def make_interval(
    df: pd.DataFrame,
    to_split_col:str='datetime',
    interval=3600,
    max_splits=100000,
    callback_error=None,
) -> L(pd.DataFrame):
    """Will check if column `to_split_col` in `df` has interval size of `interval`,
    if not will make it happen and return a list where this is done.

    This works both when type of `to_split_col` is numeric or `pd.Timestamp`

    """
    tmf = ToElapsed()
    df[to_split_col] = tmf(df[to_split_col])
    df.index = df[to_split_col]
    df = df.sort_index()
    index = df.index.to_numpy()
    df["delta"] = abs(
        (df[to_split_col] - df[to_split_col].shift(1))
    )
    mask = df["delta"] != interval
    starts = np.arange(len(mask))[mask]
    ends = list(starts[1:])+L(len(mask))

    del df["delta"]

    if len(ends) > max_splits:
        if callback_error:
            callback_error()
        raise Exception(
            f"number of splits {len(not_hour)} > {max_splits}: \n{not_hour}"
        )
#     print(starts,ends)
    dfs = L()
    for start, end in zip(starts, ends):
        _df = df.iloc[start: end,:]
        _df.loc[:,to_split_col] = tmf.decode(_df[to_split_col])
        dfs.append(_df)

    return dfs

# Cell
def melted_ts_2_lists(ts:pd.DataFrame, melted_col_name:str, fn=noop, **kwargs)->L:
    dfs = L()
    for c in set(ts[melted_col_name]):
        _df = ts[ts[melted_col_name] == c]
        r = fn(_df,**kwargs)
        dfs += r
    return dfs