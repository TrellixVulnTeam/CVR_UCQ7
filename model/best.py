import numpy as np
import torch
import torch.nn as nn
import torchvision.models as models
from models.transformer.encoders import EncoderLayer,EncoderLayer_BN
from models.transformer.utils import PositionWiseFeedForward,PositionWiseFeedForward_BN
from .Model import Model
from tools.view_gcn_utils import *
from otk.layers import OTKernel
from otk.utils import normalize
from models.Vit import TransformerEncoderLayer,TransformerEncoderLayer_noff

mean = torch.tensor([0.485, 0.456, 0.406],dtype=torch.float, requires_grad=False)
std = torch.tensor([0.229, 0.224, 0.225],dtype=torch.float, requires_grad=False)
def flip(x, dim):
    xsize = x.size()
    dim = x.dim() + dim if dim < 0 else dim
    x = x.view(-1, *xsize[dim:])
    x = x.view(x.size(0), x.size(1), -1)[:, getattr(torch.arange(x.size(1) - 1,
                                                                 -1, -1), ('cpu', 'cuda')[x.is_cuda])().long(), :]
    return x.view(xsize)

class SVCNN(Model):
    def __init__(self, name, nclasses=40, pretraining=True, cnn_name='resnet18'):
        super(SVCNN, self).__init__(name)
        if nclasses == 40:
            self.classnames = ['airplane', 'bathtub', 'bed', 'bench', 'bookshelf', 'bottle', 'bowl', 'car', 'chair',
                               'cone', 'cup', 'curtain', 'desk', 'door', 'dresser', 'flower_pot', 'glass_box',
                               'guitar', 'keyboard', 'lamp', 'laptop', 'mantel', 'monitor', 'night_stand',
                               'person', 'piano', 'plant', 'radio', 'range_hood', 'sink', 'sofa', 'stairs',
                               'stool', 'table', 'tent', 'toilet', 'tv_stand', 'vase', 'wardrobe', 'xbox']
        elif nclasses==15:
            self.classnames = ['bag', 'bed', 'bin', 'box', 'cabinet', 'chair', 'desk', 'display'
                , 'door', 'pillow', 'shelf', 'sink', 'sofa', 'table', 'toilet']
        else:
            self.classnames = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11',
                               '12', '13', '14', '15', '16', '17', '18', '19', '20', '21',
                               '22', '23', '24', '25', '26', '27', '28', '29', '30', '31',
                               '32', '33', '34', '35', '36', '37', '38', '39', '40', '41',
                               '42', '43', '44', '45', '46', '47', '48', '49', '50', '51', '52', '53', '54']

        self.nclasses = nclasses
        self.pretraining = pretraining
        self.cnn_name = cnn_name
        self.use_resnet = cnn_name.startswith('resnet')
        self.mean = torch.tensor([0.485, 0.456, 0.406],dtype=torch.float, requires_grad=False)
        self.std = torch.tensor([0.229, 0.224, 0.225],dtype=torch.float, requires_grad=False)

        if self.use_resnet:
            if self.cnn_name == 'resnet18':
                self.net = models.resnet18(pretrained=self.pretraining)
                self.net.fc = nn.Linear(512, self.nclasses)
            elif self.cnn_name == 'resnet34':
                self.net = models.resnet34(pretrained=self.pretraining)
                self.net.fc = nn.Linear(512, self.nclasses)
            elif self.cnn_name == 'resnet50':
                self.net = models.resnet50(pretrained=self.pretraining)
                self.net.fc = nn.Linear(2048, self.nclasses)
        else:
            if self.cnn_name == 'alexnet':
                self.net_1 = models.alexnet(pretrained=self.pretraining).features
                self.net_2 = models.alexnet(pretrained=self.pretraining).classifier
            elif self.cnn_name == 'vgg11':
                self.net_1 = models.vgg11_bn(pretrained=self.pretraining).features
                self.net_2 = models.vgg11_bn(pretrained=self.pretraining).classifier
            elif self.cnn_name == 'vgg16':
                self.net_1 = models.vgg16(pretrained=self.pretraining).features
                self.net_2 = models.vgg16(pretrained=self.pretraining).classifier

            self.net_2._modules['6'] = nn.Linear(4096, self.nclasses)

    def forward(self, x):
        if self.use_resnet:
            return self.net(x)
        else:
            y = self.net_1(x)
            return self.net_2(y.view(y.shape[0], -1))

class view_GCN(Model):
    def __init__(self,name, model, nclasses=40, cnn_name='resnet18', num_views=20):
        super(view_GCN,self).__init__(name)
        if nclasses == 40:
            self.classnames = ['airplane', 'bathtub', 'bed', 'bench', 'bookshelf', 'bottle', 'bowl', 'car', 'chair',
                               'cone', 'cup', 'curtain', 'desk', 'door', 'dresser', 'flower_pot', 'glass_box',
                               'guitar', 'keyboard', 'lamp', 'laptop', 'mantel', 'monitor', 'night_stand',
                               'person', 'piano', 'plant', 'radio', 'range_hood', 'sink', 'sofa', 'stairs',
                               'stool', 'table', 'tent', 'toilet', 'tv_stand', 'vase', 'wardrobe', 'xbox']
        elif nclasses==15:
            self.classnames = ['bag', 'bed', 'bin', 'box', 'cabinet', 'chair', 'desk', 'display'
                , 'door', 'pillow', 'shelf', 'sink', 'sofa', 'table', 'toilet']
        else:
            self.classnames = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11',
                               '12', '13', '14', '15', '16', '17', '18', '19', '20', '21',
                               '22', '23', '24', '25', '26', '27', '28', '29', '30', '31',
                               '32', '33', '34', '35', '36', '37', '38', '39', '40', '41',
                               '42', '43', '44', '45', '46', '47', '48', '49', '50', '51', '52', '53', '54']
        self.nclasses = nclasses
        self.mean = torch.tensor([0.485, 0.456, 0.406], dtype=torch.float, requires_grad=False)
        self.std = torch.tensor([0.229, 0.224, 0.225], dtype=torch.float, requires_grad=False)
        self.use_resnet = cnn_name.startswith('resnet')
        if self.use_resnet:
            self.net_1 = nn.Sequential(*list(model.net.children())[:-1])
            self.net_2 = model.net.fc
        else:
            self.net_1 = model.net_1
            self.net_2 = model.net_2
        self.num_views = num_views
        self.zdim = 8
        self.tgt=nn.Parameter(torch.Tensor(self.zdim,512))
        nn.init.xavier_normal_(self.tgt)
        self.coord_encoder = nn.Sequential(
            nn.Linear(512,64),
            nn.ReLU(),
            nn.Linear(64,3)
        )
        self.coord_decoder = nn.Sequential(
            nn.Linear(3,64),
            nn.ReLU(),
            nn.Linear(64,512)
        )
        self.otk_layer = OTKernel(in_dim=512, out_size=self.zdim, heads=1, max_iter=100, eps=0.05)
        self.dim = 512
        # self.encoder1 = TransformerEncoderLayer(d_model=self.dim, nhead=8)
        self.encoder_meshed1 = EncoderLayer(d_model=512, d_k=512, d_v=512, h=8, d_ff=2048, dropout=0)
        self.ff1 = PositionWiseFeedForward(d_model=512,d_ff=2048,dropout=0)
        # self.encoder2 = TransformerEncoderLayer_woff(d_model=self.dim, nhead=8)
        self.encoder_meshed2 = EncoderLayer_BN(d_model=512, d_k=512, d_v=512, h=8, d_ff=2048, dropout=0)
        self.ff2 = PositionWiseFeedForward_BN(d_model=512,d_ff=2048,dropout=0)
        self.ff3 = PositionWiseFeedForward_BN(d_model=512, d_ff=2048,dropout=0)
        self.cls = nn.Sequential(
            # nn.Linear(512, 512),
            # nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(512 , 256),
            nn.Dropout(),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Linear(256,self.nclasses)
        )
        self.cls2 = nn.Linear(512,self.nclasses)
        # for m in self.modules():
        #    if isinstance(m,nn.Linear):
        #        nn.init.kaiming_uniform_(m.weight)
        #    elif isinstance(m,nn.Conv1d):
        #        nn.init.kaiming_uniform_(m.weight)
    def forward(self,x,rand_view_num,N):
        y = self.net_1(x)
        y = y.squeeze()
        y = my_pad_sequence(sequences=y, view_num=rand_view_num, N=N, max_length=self.num_views, padding_value=0)
        mask = generate_mask(rand_view_num, N, max_len=self.num_views)
        mask_encoder = torch.bitwise_not(mask)
        # y0 = self.encoder1(src=y0.transpose(0,1), src_key_padding_mask=mask_encoder, pos=None)
        # y0 = y0.transpose(0,1)
        y0 = self.encoder_meshed1(y, y, y, attention_mask=mask_encoder)
        y0 = self.ff1(y0)
        y1 = self.otk_layer(y0,mask)
        y1 = self.ff2(y1)
        pos0 = normalize(self.coord_encoder(y1))
        pos = self.coord_decoder(pos0)
        # y2 = self.encoder2(src=y1.transpose(0,1),src_key_padding_mask=None, pos=pos.transpose(0,1))
        y2 = self.encoder_meshed2(y1+pos, y1+pos, y1, attention_mask=None)
        y2 = self.ff3(y2)
        # y2 = y2.transpose(0,1)
        weight = self.otk_layer.weight
        cos_sim = torch.matmul(normalize(weight), normalize(weight).transpose(1, 2)) - torch.eye(self.zdim,
                                                                                                 self.zdim).cuda()
        cos_sim2 = torch.matmul(normalize(y1), normalize(y1).transpose(1, 2)) - torch.eye(self.zdim, self.zdim).cuda()
        # pooled_view = y2.reshape(-1,8*512)
        # pooled_view0 = y.mean(1)
        pooled_view = y2.mean(1)
        # pooled_view2 = y0.mean(1)
        # pooled_view3 = y1.mean(1)
        # feature = self.cls(pooled_view)
        pooled_view = self.cls(pooled_view)
        return pooled_view,cos_sim,cos_sim2,pos0