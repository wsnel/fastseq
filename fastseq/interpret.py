# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/07_interpret.ipynb (unless otherwise specified).

__all__ = ['NBeatsInterpretation', 'add_stack']

# Cell
from .all import *
from .data.external import *
from fastai2.basics import *
from .models.nbeats import *

# Cell
class NBeatsInterpretation():
    "Interpretation base class, can be inherited for task specific Interpretation classes"
    def __init__(self, dl, inputs, preds, targs, decoded, losses, dct = None):
        store_attr(self, "dl,inputs,preds,targs,decoded,losses,dct")

    @classmethod
    def from_learner(cls, learn, ds_idx=1, dl=None, act=None):
        "Construct interpretatio object from a learner"
        if dl is None: dl = learn.dbunch.dls[ds_idx]
        res = learn.get_preds(dl=dl, with_input=True, with_loss=True, with_decoded=True, act=None)
        dct = learn.n_beats_trainer.out
        return cls(dl, *res, dct=dct)

    def top_losses(self, k=None, largest=True):
        "`k` largest(/smallest) losses and indexes, defaulting to all losses (sorted by `largest`)."
        return self.losses.topk(ifnone(k, len(self.losses)), largest=largest)

    def plot_top_losses(self, k, largest=True, **kwargs):
        losses,idx = self.top_losses(k, largest)
        total_b = self.dct.pop('total_b')[idx, :]
        backwards = {block+'_b':self.dct[block]['b'][idx,:] for block in self.dct}
        forwards = {block+'_f':self.dct[block]['f'][idx,:] for block in self.dct}

        if not isinstance(self.inputs, tuple): self.inputs = (self.inputs,)
        if isinstance(self.inputs[0], Tensor): inps = tuple(o[idx] for o in self.inputs)
        else: inps = self.dl.create_batch(self.dl.before_batch([tuple(o[i] for o in self.inputs) for i in idx]))
        b = inps + tuple(o[idx] for o in (self.targs if is_listy(self.targs) else (self.targs,)))
        x,y,its = self.dl._pre_show_batch(b, max_n=k)
        b_out = inps + tuple(o[idx] for o in (self.decoded if is_listy(self.decoded) else (self.decoded,)))
        x1,y1,outs = self.dl._pre_show_batch(b_out, max_n=k)
        if its is not None:
            plot_top_losses(x, y, its, outs.itemgot(slice(len(inps), None)), self.preds[idx], losses, b=backwards, f=forwards, total_b=total_b, **kwargs)
#         #TODO: figure out if this is needed
#         #its None means that a batch knos how to show itself as a whole, so we pass x, x1
#         else:
#         show_results(x, x1, its, ctxs=ctxs, max_n=max_n, **kwargs)

# Cell
def add_stack(b):
    res = {}
    for stack in set([o[:-4] for o in b.keys()]):
        for direction in ['f','b']:
            for key in b.keys():
                if stack in key and direction == key[-1]:
                    if stack+'_'+direction in res:
                        res[stack+'_'+direction] += b[key]
                    else:
                        res[stack+'_'+direction] = b[key]
    return res



# Cell
@typedispatch
def plot_top_losses(x:TSTensorSeq, y:TSTensorSeqy, *args, b={}, f={}, total_b=None, combine_stack=True,
                    rows=None, cols=None, figsize=None, **kwargs):

    figsize = (2*3, x.shape[0]*3+0) if figsize is None else figsize
    _, axs = plt.subplots(x.shape[0], 2, figsize=figsize, sharey='row')
    axs = axs.flatten()
    normal = np.arange(0,x.shape[0]*2,2)
    if combine_stack:
        b = add_stack(b)
        f = add_stack(f)
    for i, (_x, _y, pred, t) in enumerate(zip(x, y, args[2], args[3])):
        ax = axs[i*2]
        ctx = show_graph(_x, ax=ax, title=str(t.data))
        a = [TSTensorSeqy(_y, x_len = x.shape[-1], m = '-g'), TSTensorSeqy(pred,x_len = x.shape[-1], m = '-*r')]
        if 'total_b' is not None:
            ctx = TSTensorSeqy(-total_b[i,:], m = '-*r',label='y_backwards').show(ctx=ctx)
        for y in a:
            ctx = y.show(ctx=ctx)
        ax = axs[i*2 + 1]
        total = torch.zeros_like(b[list(b.keys())[0]][i,:])
        for k_f, k_b, c in zip(f.keys(),b.keys(), ['y','k','g','r','b','b','b','b']):
            ax = TSTensorSeqy(f[k_f][i,:],x_len = x.shape[-1], m = '-*'+c, label = k_f).show(ctx=ax)
            ax = TSTensorSeqy(b[k_b][i,:], m = '-*'+c, label= k_b).show(ctx=ax)
            total += b[k_b][i,:]

#         ax = TSTensorSeqy(total, m = '-*y', label= 'tot').show(ctx=axs[i*2])
        ax.legend(bbox_to_anchor=(1.3, 1.05))

