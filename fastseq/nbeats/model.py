# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/05_nbeats.models.ipynb (unless otherwise specified).

__all__ = ['linspace', 'make_base', 'Block', 'SeasonalityModel', 'SeasonalityBlock', 'trend_model', 'TrendBlock',
           'select_block', 'default_thetas', 'NBeatsNet']

# Cell
from fastcore.utils import *
from fastcore.imports import *
from fastai2.basics import *
from fastai2.callback.hook import num_features_model
from fastai2.callback.all import *
from fastai2.layers import *
from fastai2.torch_core import *
from torch.autograd import Variable
from ..all import *

# Cell
def linspace(lookback, horizon,device=None):
    device = ifnone(device, default_device())
    lin_space = torch.linspace(
        -lookback+1, horizon, lookback + horizon, requires_grad=False
    ).to(device)
    b_ls = Variable(lin_space[:lookback])
    f_ls = Variable(lin_space[lookback:])
    return b_ls, f_ls

# Cell
def make_base(u_in, layers,use_bn,ps):
    sizes = L(u_in) + layers
    ps = ifnone(ps, L([0]) * len(layers))
    actns = [Mish() for _ in range(len(sizes)-1)]
    _layers = [LinBnDrop(sizes[i], sizes[i+1], bn=use_bn, p=p, act=a)
                   for i,(p,a) in enumerate(zip(ps, actns))]
    return nn.Sequential(*_layers)

# Cell
class Block(Module):
    def __init__(self, fnc_f, fnc_b=None, base=None, **kwargs):
        self.base = ifnone(base, make_base(self.lookback, self.layers, self.use_bn, self.ps))

        self.att = self.__dict__.get('att', None)
        if self.att:
            self.att = LinBnDrop(self.layers[-1], self.thetas_dim)
        if self.share_thetas:
            self.theta_fc = LinBnDrop(self.layers[-1], self.thetas_dim)
        else:
            self.theta_b_fc = LinBnDrop(self.layers[-1], self.thetas_dim)
            self.theta_f_fc = LinBnDrop(self.layers[-1], self.thetas_dim)
            print('not going to share thetas')
        self.theta_scale = LinBnDrop(self.layers[-1], self.thetas_dim)
        self.theta_range = LinBnDrop(self.layers[-1], 1)

        self.fnc_f = fnc_f
        self.fnc_b = ifnone(fnc_b, fnc_f)
        self.to(self.device)
        self.y_range = getattr(self,'y_range', None)


    def forward(self, x, b, f):
        res = {}
        x = self.base(x)
        if self.share_thetas:
            theta_b = self.theta_fc(x)
            theta_f = self.theta_fc(x)
        else:
            theta_b = self.theta_b_fc(x)
            theta_f = self.theta_f_fc(x)

        if self.att:
            w = torch.sigmoid(self.att(x))
            theta_b, theta_f = theta_b * w, theta_b * w
            res['attention'] = w

        scale = self.theta_scale(x)
        rang = self.theta_scale(x)
        theta_b = self.apply_range(theta_b, scale, rang)
        theta_f = self.apply_range(theta_f, scale, rang)
#         b, f = linspace(self.lookback, self.horizon, device = self.device)
        backcast = self.fnc_b(theta_b, b)
        forecast = self.fnc_f(theta_f, f)
        res.update({'b':backcast,'f': forecast, 'theta': (theta_b + theta_f)})
        return res

    def apply_range(self, x, scale, rang):
        if self.y_range is None:
            return x
        rang = 0.5 + torch.sigmoid(rang)
        y_range = self.y_range[0] * rang, self.y_range[1] * rang

        r = (y_range[1]-y_range[0]) * torch.sigmoid(x) + y_range[0]
        scale = .5 + torch.sigmoid(scale)
        return r *(self.scale*scale)

# Cell
class SeasonalityModel(object):
    """Returns a function with `period` being the period of least frequent aproximations function. """
    def __init__(self, period=None):
        self.period = period

    def __call__(self, thetas, t, *args):
        p = thetas.size()[-1]
        assert p < 12, f"thetas_dim is too big. p = {p}"
        p1, p2 = (p // 2, p // 2) if p % 2 == 0 else (p // 2, p // 2 + 1)
        period = ifnone(self.period, ((t.max()-t.min()))*2)
        freq_scale = 1*2**-(torch.arange(float(p)))
        s1 = [torch.cos((np.pi/(.5* period * freq_scale[i] ))*t)[None,:] for i in range(p1)] # H/2-1
        s2 = [torch.sin((np.pi/(.5* period * freq_scale[i] ))*t)[None,:] for i in range(p2)]
        S = torch.cat([*s1, *s2])
        return thetas.mm(S)

# Cell
class SeasonalityBlock(Block):
    def __init__(
        self, layers:L, thetas_dim:int, device, lookback=10, horizon=5, use_bn=True, season = None,
            bn_final=False, ps:L=None, share_thetas=True, y_range=[-.5,.5], att=True, scale_exp = 4, stand_alone=False, base = None, **kwargs
    ):
        store_attr(self,"y_range,device,layers,thetas_dim,use_bn,ps,lookback,horizon,bn_final,share_thetas,att,stand_alone,base" )
        half_dim =self.thetas_dim//2 if self.thetas_dim%2 == 0 else self.thetas_dim//2+1
        s = 1*scale_exp**-(torch.arange(float(half_dim))).to(self.device)
        if self.thetas_dim %2 == 0:
            self.scale = torch.cat([s,s])
        else:
            self.scale = torch.cat([s,s[:-1]])
        season = ifnone(season, self.horizon)
        super().__init__(SeasonalityModel(season))
        self.to(device)

    def forward(self, x):
        b, f = linspace(self.lookback, self.horizon, device = self.device)
        if self.stand_alone:
            dct = super().forward(x[:,0,:], b, f)
            return torch.cat([dct['b'][:,None,:], dct['f'][:,None,:]],dim=-1)
        else:
            return super().forward(x, b, f)

# Cell
def trend_model(thetas, t):
    s = tensor(thetas.shape[-1]/2).int()

    bias = thetas[:,s:]
    thetas = thetas[:,:s]
    assert bias.shape == thetas.shape, f"{bias.shape} {thetas.shape}"
    p = thetas.size()[-1]
    assert p <= 4, f"thetas_dim is too big. p={p}"
    a =[]
    for i in range(p):
        _t = t[None,:] + bias[:,i][:,None]
        exp = torch.pow(_t, i)
        a.append((thetas[:,i][:,None] * exp)[:,:,None])
#     print([o.shape for o in a])
    T = torch.cat(a,-1).float()
    return torch.sum(T,-1)
# def trend_model(thetas, t):
#     p = thetas.size()[-1]
#     assert p <= 4, f"thetas_dim is too big. p={p}"
#     a = [torch.pow(t, i)[None,:] for i in range(p)]
#     T = torch.cat(a).float()
#     return thetas.mm(T)

# Cell
class TrendBlock(Block):
    def __init__(
        self, layers:L, device, thetas_dim, lookback=10, horizon=5, use_bn=True,
        bn_final=False, ps:L=None, share_thetas=True, y_range=[-.1, .1], att = True, scale_exp = 10,stand_alone=False,base=None,**kwargs
    ):
        store_attr(self,"y_range,device,layers,thetas_dim,use_bn,ps,lookback,horizon,bn_final,share_thetas,att,stand_alone,base" )
        self.scale = 1*scale_exp**-(torch.arange(float(self.thetas_dim))).to(self.device)
#         self.scale = 1*scale_exp**-(torch.arange(float(self.thetas_dim))).to(self.device)
        self.thetas_dim = self.thetas_dim*2
        self.scale = torch.cat([self.scale,3*torch.ones_like(self.scale)])
        self.scale[0]=3
        super().__init__(trend_model)
        self.to(device)

    def forward(self, x):
        b, f = linspace(self.lookback, self.horizon, device = self.device)
        if self.stand_alone:
            dct = super().forward(x[:,0,:], b, f)
            return torch.cat([dct['b'][:,None,:], dct['f'][:,None,:]],dim=-1)
        else:
            return super().forward(x, b, f)

# Cell

# not pritty but still works better
def select_block(o):
    if isinstance(o,int):
        if o == 0:
            return SeasonalityBlock
        elif o == 1:
            return TrendBlock
        elif o == 2:
            return BaisBlock
        else:
            return GenericBlock
    else:
        if o == 'seasonality':
            return SeasonalityBlock
        elif o == 'trend':
            return TrendBlock
        elif o =='bias':
            return BiasBlock
        else:
            return GenericBlock

default_thetas={'seasonality':6,'trend':4,'bais':2}

# Cell
class NBeatsNet(Module):
    def __init__(
        self,
        device,
        stack_types=('trend', 'seasonality'),
        nb_blocks_per_stack=3,
        horizon=5,
        lookback=10,
        thetas_dim=None,
        share_weights_in_layers=True,
        layers= [1024,512],
        norm=False,
        **kwargs,
    ):
        thetas_dim = ifnone(thetas_dim,[default_thetas[o] for o in L(stack_types)])
        stack_types= L(stack_types)
        self.eps, self.m, self.s = Variable(tensor(1e-7), requires_grad=False).to(device),Variable(tensor(1e-7), requires_grad=True).to(device),Variable(tensor(1e-7), requires_grad=True).to(device)
        store_attr(self,'device,horizon,lookback,layers,nb_blocks_per_stack,share_weights_in_layers,stack_types,thetas_dim,device,norm,kwargs')
        self.stacks = []
        self._str = "| N-Beats\n"

        self.bn = BatchNorm(lookback, ndim=2)
        stacks = OrderedDict()
        self.base = None
        if self.share_weights_in_layers:
            self.base = make_base(self.lookback, self.layers, True, None)
        for stack_id in range(len(self.stack_types)):
            stacks[str(self.stack_types[stack_id]) + str(stack_id)] = self.create_stack(stack_id)
        self.stacks = nn.Sequential(stacks)

    def create_stack(self, stack_id):
        stack_type = self.stack_types[stack_id]
        self._str += f"| --  Stack {stack_type.title()} (#{stack_id}) (share_weights_in_stack={self.share_weights_in_layers})\n"

        blocks = []
        for thetas_dim in range(3,self.thetas_dim[stack_id]+1):
            block_init = select_block(stack_type)
            block = block_init(
                layers = self.layers,
                thetas_dim = thetas_dim,
                device = self.device,
                lookback = self.lookback,
                horizon = self.horizon,
                base = self.base,
                **self.kwargs
                )
            self._str += f"     | -- {block}\n"
            blocks.append(block)

        return nn.Sequential(*blocks)

    def iter_blocks(self):
        for stack_id, names in enumerate(self.stacks.named_children()):
            name = names[0]
            for block_id in range(len(self.stacks[stack_id])):
                yield name, stack_id, block_id, self.stacks[stack_id][block_id]

    def forward(self, x):
        self.dct = None
        if self.norm:
            self.m, self.s = torch.mean(x,-1,keepdim=True), x.std(-1,keepdim=True) + self.eps
            x = (x-self.m)/self.s
            print('requires_grad',x.requires_grad)
        backcast_res = x.view([-1,x.shape[-1]])
        backcast = torch.zeros(
            size=(backcast_res.size()[0], self.lookback,)
        )
        forecast = torch.zeros(
            size=(backcast.size()[0], self.horizon,)
        )  # maybe batch size here.

        dct = defaultdict(dict)
        for stack_id, names in enumerate(self.stacks.named_children()):
            name = names[0]
            for block_id in range(len(self.stacks[stack_id])):
                _dct = self.stacks[stack_id][block_id](backcast_res)
                backcast_res = backcast_res.to(self.device) - _dct['b']

                backcast = backcast.to(self.device) + _dct['b']
                forecast = forecast.to(self.device) + _dct['f']
                _dct['_full'] = torch.cat([_dct['b'] , _dct['f']], dim=-1)
                dct[name+'_'+str(block_id)] = _dct

        dct['f'] = forecast[:,None,:]
        dct['b'] = backcast[:,None,:]
        self.dct = dct
        res = torch.cat([backcast[:,None,:], forecast[:,None,:]], dim=-1)
        if self.norm:
            return (res*self.s)+self.m
        return res

    def __setattr__(self, key, value):
        if key in ['lookback','horizon']:
            if hasattr(self,'stacks'):
                for name, stack_id, block_id, stack in self.iter_blocks():
                    setattr(stack, key, value)
        super().__setattr__(key, value)