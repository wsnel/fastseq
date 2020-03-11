# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/020_data.load_pd.ipynb (unless otherwise specified).

__all__ = ['TSMulti', 'TensorCatI', 'CatSeqI', 'unpack_list', 'CatTfm', 'TSMulti_', 'CatMultiTfm', 'array2series',
           'arrays2series', 'reconize_cols', 'PrepDF', 'same_size_ts', 'make_ids', 'get_id', 'DfDataLoader',
           'to_contained_series']

# Cell
from ..core import *
from .external import *
from fastcore.utils import *
from fastcore.imports import *
from fastai2.basics import *
from fastai2.data.transforms import *
from fastai2.tabular.core import *

# Cell
import numpy as np
import pandas as pd

# Cell
class TSMulti(MultiTuple):pass

# Cell
class TensorCatI(TensorBase):pass
class CatSeqI(TensorSeqs):pass
def unpack_list(o, r=None):
    r = ifnone(r,L())
    for a in o:
        if isinstance(a,list) or isinstance(a,L):
            r = unpack_list(a, r)
        else:
            r.append(a)
    return r

class CatTfm(Transform):
    def __init__(self, df, cat_cols:[]): # maybe change to proccs
        self.vocab,self.o2i = {},{}
        for i, col in enumerate(L(cat_cols)):
            r = unpack_list(list(df[col]))
            self.vocab[col], self.o2i[col] = uniqueify(r, sort=True, bidir=True)

    def encodes(self, x:TensorCat):
        r = []
        for i, (o, key) in enumerate(zip(x.o, x._meta['label'])):
            r.append(self.o2i[key][o])#TensorCat
        return TensorCatI(r, label = x._meta['label'])

    def decodes(self, x:TensorCatI):
        r = []
        for i,(o, key) in enumerate(zip(x,x._meta['label'])):
            r.append(self.vocab[key][o]) #TensorCat
        return TensorCat(r, label = x._meta['label'])

    def encodes(self, x:CatSeq):
        r = []
        for i,(o, key) in enumerate(zip(x.o,x._meta['label'])):
            r.append([])
            for a in o:
                r[i].append(self.o2i[key][a]) #CatSeq
        return CatSeqI(r, label = x._meta['label'])

    def decodes(self, x:CatSeqI):
        r = []
        for i, (o, key) in enumerate(zip(x,x._meta['label'])):
            r.append([])
            for a in o:
                r[i].append(self.vocab[key][a])
        return CatSeq(r, label = x._meta.get('label',None))



# Cell
class TSMulti_(Tuple):pass

class CatMultiTfm(ItemTransform):
    @delegates(CatTfm.__init__)
    def __init__(self, *args, **kwargs): # maybe change to proccs
        self.f = CatTfm(*args, **kwargs)

    def encodes(self, o:TSMulti):
        return TSMulti_(self.f(a) for a in o)

    def decodes(self, o:TSMulti_):
        return TSMulti(self.f.decode(a) for a in o)


# Cell
def array2series(o):
    return pd.Series(o.flatten())
def arrays2series(s:pd.Series):
    return pd.Series([array2series(o) for o in s])

# Cell
def reconize_cols(dataset, col_types = {}):
    con_names, cat_names, con_ts_names, cat_ts_names, classes = L(), L(), L(), L(), {}
    for col in dataset.columns:
        t = type(dataset[col].iloc[0])
        if t is pd.core.series.Series:
            con_ts_names.append(col)
        elif t is np.ndarray:
            o = arrays2series(dataset[col])
            dataset[col] = o
            con_ts_names.append(col)
        elif isinstance(dataset[col].iloc[0], str):
            cat_names.append(col)
            classes[col] = uniqueify(list(dataset[col].values))
        elif isinstance(dataset[col].iloc[0], float) or isinstance(dataset[col].iloc[0], int) or t is np.int64:
            con_names.append(col)
        elif (isinstance(dataset[col].iloc[0], L) or isinstance(dataset[col].iloc[0],list)) and isinstance(dataset[col].iloc[0][0],str):
            cat_ts_names.append(col)
            classes[col] = uniqueify(unpack_list(list(dataset[col])))
        else:
            raise Exception(t)
    return con_names, cat_names, con_ts_names, cat_ts_names, classes, dataset

# Cell
class PrepDF(TabularProc):
    def setup(self, dl, train_setup):
        # speed up retrival
        dl.con = dl.dataset.loc[:,dl.con_names].values.astype(float)
        dl.cat = [list(dl.dataset.loc[i,dl.cat_names]) for i in range(dl.dataset.shape[0])]
        if len(dl.con_ts_names):
            dl.tsx_con = [np.concatenate([o[None,:] for o in dl.dataset.loc[i,dl.con_ts_names].values]) for i in range(dl.dataset.shape[0])]
        else:
            dl.tsx_con = [np.empty([0,0]) for i in range(dl.dataset.shape[0])]

        if len(dl.cat_ts_names):
            dl.tsx_cat = list([L([a for a in o]) for o in df[dl.cat_ts_names].values])
        else:
            dl.tsx_cat = ['']*dl.dataset.shape[0]
        assert len(dl.cat) == len(dl.tsx_con) == dl.con.shape[0] == len(dl.tsx_cat), f"{len(dl.cat)} == {len(dl.tsx_con)} == {dl.con.shape[0]} == {len(dl.tsx_cat)}"
        return dl

# Cell
def same_size_ts(ts:pd.Series, ts_names, _raise = True):
    shapes = {k:ts[k].shape if hasattr(ts[k],'shape') else (len(ts[k]),) for k in ts_names}
    all_same = [[(shapes[c] == shapes[a]) for c in ts_names] for a in ts_names]
    mask = np.array(all_same)
    if _raise:
        assert np.sum(mask) == len(ts_names)**2, shapes
    return np.sum(mask) == len(ts_names)**2


# Cell
def make_ids(dl):
    """Make ids if the sequence is shorter than `min_seq_len`, it will drop that sequence."""
    # Slice each time series into examples, assigning IDs to each
    last_id = 0
    n_dropped = 0
    n_needs_padding = 0
    dl._ids = {}
    for i, ts in dl.dataset.iterrows():
        same_size_ts(ts, dl.con_ts_names + dl.cat_ts_names)
        num_examples = (ts[dl.y_name].shape[-1] - dl.lookback - dl.horizon + dl.step) // dl.step
        # Time series shorter than the forecast horizon need to be dropped.
        if ts[dl.y_name].shape[-1] < dl.min_seq_len:
            n_dropped += 1
            continue
        # For short time series zero pad the input
        if ts[dl.y_name].shape[-1] < dl.lookback + dl.horizon:
            n_needs_padding += 1
            num_examples = 1
        for j in range(num_examples):
            dl._ids[last_id + j] = (i, j * dl.step)
        last_id += num_examples

    # Inform user about time series that were too short
    if n_dropped > 0:
        print("Dropped {}/{} time series due to length.".format(
                n_dropped, len(dl.dataset)))

    # Inform user about time series that were short
    if n_needs_padding > 0:
        print("Need to pad {}/{} time series due to length.".format(
                n_needs_padding, len(dl.dataset)))
    # Store the number of training examples
    dl.n = int(dl._ids.__len__() )
    return dl, int(dl._ids.__len__() )


# Cell
@typedispatch
def get_part_of_ts(x, lookback_id, length, pad=np.mean, t = tensor, **kwargs):
#     if len(x.shape) == 1:
#         x = x[None,:]
#     if isinstance(x[0,0],int):
#         x = x.astype(float)
    if x.shape[-1] < length:
        # If the time series is too short, we pad
        padding = pad(x, -1)
        x = t(np.pad(
            x, # report issue https://github.com/numpy/numpy/issues/15606
            pad_width=((0, 0), (length - x.shape[-1], 0)),
            mode='constant',
            constant_values=padding
        ), **kwargs).float()
        assert x.shape == (x.shape[0],length), f"{x.shape}\t,{lookback_id}, 'tsshape':{x.shape}"
    else:
        x = t(x[:,lookback_id:lookback_id + length], **kwargs).float()
    return x


# Cell
@typedispatch
def get_part_of_ts(x:L, lookback_id, length, t = L, **kwargs):
    if len(x[0]) < length:
        # If the time series is too short, we pad
        padding = [o[-1] for o in x]
        pad_len = length - len(x[0])
        x = t(L(o[lookback_id:lookback_id + length] + [padding[i]]*pad_len) for i,o in enumerate(x))
    else:
        x = t([o[lookback_id:lookback_id + length] for o in x], **kwargs)
    return x

# Cell
from ..core import *
def get_id(dl, ts_id, lookback_id):
    y = get_part_of_ts(dl.dataset.loc[ts_id, dl.y_name].values[None,:], lookback_id, dl.lookback + dl.horizon,
                       t = TensorSeqs, label=[dl.y_name + '_y'], m=['g'])
    x = TensorSeqs(y[:,:dl.lookback], label=[dl.y_name + '_x'], m=['g'])
    if len(dl.con_ts_names):
        tsx_con = get_part_of_ts(dl.tsx_con[ts_id], lookback_id, dl.lookback + dl.horizon,
                             t = TensorSeqs, label=dl.con_ts_names)
    else: tsx_con = TensorSeqs(np.empty([0]), label=[dl.con_ts_names])
    if len(dl.cat_ts_names):
        tsx_cat = get_part_of_ts(dl.tsx_cat[ts_id], lookback_id, dl.lookback + dl.horizon,
                             t = CatSeq, label=dl.cat_ts_names)
    else: tsx_cat = CatSeq('', label=dl.cat_ts_names)

    r = [x, tsx_con, tsx_cat]
    r.append(TensorCat(dl.cat[ts_id], label=dl.cat_names))
    r.append(TensorCon(dl.con[ts_id,:], label=dl.con_names))
    r.append(y)
    return tuple(r)

# Cell
@delegates()
class DfDataLoader(TfmdDL):
    def __init__(self, dataset:pd.DataFrame, y_name:str, horizon:int, lookback=72, step=1,
                 min_seq_len=None, procs = None, train = True, **kwargs):
        con_names, cat_names, con_ts_names, cat_ts_names, classes, dataset = reconize_cols(dataset)
        store_attr(self,'horizon,lookback,step,y_name,con_names,cat_names,con_ts_names,cat_ts_names,classes,dataset')
        assert y_name in self.con_ts_names, {k:getattr(self,k) for k in 'con_names,cat_names,con_ts_names,cat_ts_names'.split(',')}
        self.con_ts_names.remove(y_name)
        self.min_seq_len = ifnone(min_seq_len, lookback)
        self, n = make_ids(self)
        kwargs['after_item'] = kwargs.get('after_item', CatMultiTfm(dataset, self.cat_names+self.cat_ts_names))
        super().__init__(dataset=self.dataset, **kwargs)
        self.n = n
        self.procs = Pipeline(PrepDF() +L(procs), as_item=True)
        self.procs.setup(self, train)

    @delegates(TfmdDL.new)
    def new(self, dataset=None, cls=None, **kwargs):
        for k,v in {k:getattr(self,k) for k in ['horizon', 'lookback', 'step']}.items():
            if k not in kwargs:
                kwargs[k] = v
        res = super().new(dataset = dataset,cls= cls, y_name= self.y_name, **kwargs)
        res, n = make_ids(res)
        res.n = n
        return res

    def create_item(self, idx):
        if idx>=self.n:
            raise IndexError
        ts_id, lookback_id = self._ids[idx]
        r  = get_id(self, ts_id, lookback_id)
        return TSMulti(r)

# Cell

def _show_batch_class(self, b=None, max_n=9, ctxs=None, show=True, **kwargs):
    if b is None: b = self.one_batch()
    x, y, its = self._pre_show_batch(b, max_n=max_n)
    x = self.after_item.decode(TSMulti_(x))
    if not show: return x, y, its
    show_batch(x,y,its, ctxs=ctxs, max_n=max_n, **kwargs)

DfDataLoader.show_batch = _show_batch_class

# Cell
from fastai2.vision.data import get_grid
@typedispatch
def show_batch(x:TSMulti, y:TensorSeqs, its, *args, ctxs=None, max_n=10, rows=None, cols=None, figsize=None, **kwargs):
    if ctxs is None: ctxs = get_grid(min(x[0].shape[0], max_n), add_vert=1, figsize=figsize, **kwargs)
    for i, ctx in enumerate(ctxs):
        o = TSMulti([type(o)(o,**o._meta) for o in its[i] if o.shape[-1] > 0])
        ctx = o.show(ctx=ctx)
    return ctxs

@typedispatch
def show_batch(x:TSMulti, y:None, its, *args, ctxs=None, max_n=10, rows=None, cols=None, figsize=None, **kwargs):
    if ctxs is None: ctxs = get_grid(min(x[0].shape[0], max_n), add_vert=1, figsize=figsize, **kwargs)
    for i, ctx in enumerate(ctxs):
        o = TSMulti([type(o)(o[i],**o[i]._meta) for o in x if o.shape[-1] > 0])
        ctx = o.show(ctx=ctx)
    return ctxs

# Cell

# def _show_results_class(self, b, out, max_n=9, ctxs=None, show=True, **kwargs):
#     x,y,its = self.show_batch(b, max_n=max_n, show=False,)
#     x = self.after_item.decode(b)
#     b_out = b[:self.n_inp] + (tuple(out) if is_listy(out) else (out,))
#     x1,y1,outs = self.show_batch(b_out, max_n=max_n, show=False)
#     res = (x,x1,None,None) if its is None else (x, y, its, outs.itemgot(slice(self.n_inp,None)))
#     if not show: return res
#     show_results(*res, ctxs=ctxs, max_n=max_n, **kwargs)

# DfDataLoader.show_results = _show_results_class

# Cell
# from fastseq.data.load_pd import *

@typedispatch
def show_results(x:TSMulti, y, its, outs, ctxs=None, max_n=9,rows=None, cols=None, figsize=None, **kwargs):
    if ctxs is None: ctxs = get_grid(min(x[0].shape[0], max_n), add_vert=1, figsize=figsize, **kwargs)
    for i, ctx in enumerate(ctxs):
        r = [type(o)(o,**o._meta) for o in its[i] if o.shape[-1] > 0]
        r.append(type(its[i][-1])(outs[i][0], label=['pred_y'], m=['r']))
        o = TSMulti(r)
        ctx = o.show(ctx=ctx)


# Cell
def _to_series(df, s_slice=None, add_zeros = 28*2):
    s_slice = ifnone(s_slice, slice(6,None))
    r = []
    for i in range(df.shape[0]):
        r.append(pd.Series(np.concatenate([df.iloc[i, s_slice].values.astype(float),[0]*add_zeros]) ))
    return r

@delegates(_to_series)
def to_contained_series(df, series_column_name = 'sales', **kwargs):
    data={k:v for k,v in dict(df).items() if ('d_' not in k and 'F' not in k)}
    data[series_column_name] = pd.Series(_to_series(df, **kwargs))
    df = pd.DataFrame(data=data)
    return df