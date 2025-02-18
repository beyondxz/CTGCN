import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable
import sys, random
sys.path.append("..")
from CTGCN.utils import accuracy

class UnsupervisedLoss(nn.Module):
    node_pair_list: list
    node_freq_list: list
    neg_sample_num: int
    Q: float

    def __init__(self, neg_num=20, Q=10, node_pair_list=None, neg_freq_list=None):
        super(UnsupervisedLoss, self).__init__()
        self.neg_sample_num = neg_num
        self.Q = Q
        self.node_pair_list = node_pair_list
        self.neg_freq_list = neg_freq_list

    def forward(self, embeddings, batch_node_idxs, loss_type='connection', structure_list=None):
        if isinstance(embeddings, list):
            timestamp_num = len(embeddings)
        else: # tensor
            timestamp_num = embeddings.size()[0] if len(embeddings.size()) == 3 else 1

        if loss_type == 'connection':
            bce_loss = nn.BCEWithLogitsLoss()
            neighbor_loss = Variable(torch.FloatTensor([0.]), requires_grad=True).cuda() if torch.cuda.is_available() else Variable(torch.FloatTensor([0.]), requires_grad=True)
            for i in range(timestamp_num):
                if isinstance(embeddings, list) or len(embeddings.size()) == 3:
                    embedding_mat = embeddings[i]
                else:
                    embedding_mat = embeddings
                node_pair_dict = self.node_pair_list[i]
                node_freq = self.neg_freq_list[i]
                node_idxs, pos_idxs, neg_idxs = [], [], []

                for node_idx in batch_node_idxs:
                    neighbor_num = len(node_pair_dict[node_idx])
                    if neighbor_num <= self.neg_sample_num:
                        pos_idxs += node_pair_dict[node_idx]
                        node_idxs += [node_idx] * len(node_pair_dict[node_idx])
                    else:
                        pos_idxs += random.sample(node_pair_dict[node_idx], self.neg_sample_num)
                        node_idxs += [node_idx] * self.neg_sample_num
                assert len(node_idxs) <= len(batch_node_idxs) * self.neg_sample_num
                neg_idxs += random.sample(node_freq, self.neg_sample_num)
                if len(node_idxs) == 0 or len(pos_idxs) == 0 or len(neg_idxs) == 0:
                    continue
                ######################
                # this block is quite important, otherwise the code will cause memory leak!
                node_idxs = torch.LongTensor(node_idxs)
                pos_idxs = torch.LongTensor(pos_idxs)
                neg_idxs = torch.LongTensor(neg_idxs)
                if torch.cuda.is_available():
                    node_idxs = node_idxs.cuda()
                    pos_idxs = pos_idxs.cuda()
                    neg_idxs = neg_idxs.cuda()
                # this block is quite important, otherwise the code will cause memory leak!
                #######################
                pos_score = torch.sum(embedding_mat[node_idxs].mul(embedding_mat[pos_idxs]), dim=1)
                neg_score = -1.0 * torch.sum(embedding_mat[node_idxs].matmul(torch.transpose(embedding_mat[neg_idxs], 1, 0)), dim=1)
                pos_loss = bce_loss(pos_score, torch.ones_like(pos_score))
                neg_loss = self.Q * bce_loss(neg_score, torch.ones_like(neg_score))
                loss_val = pos_loss + neg_loss
                neighbor_loss = neighbor_loss + loss_val
                # del node_idxs, pos_idxs, neg_idxs
            return neighbor_loss
            # return self.negative_sampling_loss(embeddings, batch_node_idxs, timestamp_num)
        elif loss_type == 'structure':
            mse_loss = nn.MSELoss()
            structure_loss = Variable(torch.FloatTensor([0.]), requires_grad=True).cuda() if torch.cuda.is_available() else Variable(torch.FloatTensor([0.]), requires_grad=True)

            for i in range(timestamp_num):
                if isinstance(embeddings, list) or len(embeddings.size()) == 3:
                    embedding_mat = embeddings[i]
                    structure_mat = structure_list[i]
                else:
                    embedding_mat = embeddings
                    structure_mat = structure_list
                node_idxs = torch.LongTensor(batch_node_idxs)
                if torch.cuda.is_available():
                    node_idxs = node_idxs.cuda()
                structure_loss = structure_loss + mse_loss(structure_mat[node_idxs], embedding_mat[node_idxs])
            return structure_loss
            #return self.reconstruct_loss(embeddings, batch_node_idxs, timestamp_num, structure_list)
        else:
            raise AttributeError('Unsupported loss type!')

class SupervisedLoss(nn.Module):

    def __init__(self):
        super(SupervisedLoss, self).__init__()

    def forward(self, embeddings, batch_node_idxs, batch_labels, loss_type='connection', structure_list=None, emb_list=None):
        if isinstance(embeddings, list):
            timestamp_num = len(embeddings)
        else: # tensor
            timestamp_num = embeddings.size()[0] if len(embeddings.size()) == 3 else 1

        if loss_type == 'connection':
            log_softmax = nn.LogSoftmax(dim=1)
            nll_loss = nn.NLLLoss()
            total_loss = Variable(torch.FloatTensor([0.]), requires_grad=True).cuda() if torch.cuda.is_available() else Variable(torch.FloatTensor([0.]), requires_grad=True)
            total_acc = Variable(torch.FloatTensor([0.]), requires_grad=True).cuda() if torch.cuda.is_available() else Variable(torch.FloatTensor([0.]), requires_grad=True)
            for i in range(timestamp_num):
                if isinstance(embeddings, list) or len(embeddings.size()) == 3:
                    output_mat = embeddings[i]
                else:
                    output_mat = embeddings
                ######################
                # this block is quite important, otherwise the code will cause memory leak!
                node_idxs = torch.LongTensor(batch_node_idxs)
                labels = torch.LongTensor(batch_labels)
                if torch.cuda.is_available():
                    node_idxs = node_idxs.cuda()
                    labels = labels.cuda()
                preds = log_softmax(output_mat[node_idxs])
                # this block is quite important, otherwise the code will cause memory leak!
                #######################
                loss_val = nll_loss(preds, labels)
                acc_val = accuracy(preds, labels)
                total_loss = total_loss + loss_val
                total_acc = total_acc + acc_val
            return total_loss, total_acc
        elif loss_type == 'structure':
            mse_loss = nn.MSELoss()
            log_softmax = nn.LogSoftmax(dim=1)
            nll_loss = nn.NLLLoss()
            total_loss = Variable(torch.FloatTensor([0.]), requires_grad=True).cuda() if torch.cuda.is_available() else Variable(torch.FloatTensor([0.]), requires_grad=True)
            total_acc = Variable(torch.FloatTensor([0.]), requires_grad=True).cuda() if torch.cuda.is_available() else Variable(torch.FloatTensor([0.]), requires_grad=True)
            for i in range(timestamp_num):
                if isinstance(embeddings, list) or len(embeddings.size()) == 3:
                    output_mat = embeddings[i]
                    embedding_mat = emb_list[i]
                    structure_mat = structure_list[i]
                else:
                    output_mat = embeddings
                    embedding_mat = emb_list
                    structure_mat = structure_list
                ######################
                # this block is quite important, otherwise the code will cause memory leak!
                #node_idxs = torch.LongTensor(batch_node_idxs)
                labels = torch.LongTensor(batch_labels)
                if torch.cuda.is_available():
                    node_idxs = node_idxs.cuda()
                    labels = labels.cuda()
                preds = log_softmax(output_mat[node_idxs])
                # this block is quite important, otherwise the code will cause memory leak!
                #######################
                loss_val = nll_loss(preds, labels) + mse_loss(structure_mat[node_idxs], embedding_mat[node_idxs])
                acc_val = accuracy(preds, labels)
                total_loss = total_loss + loss_val
                total_acc = total_acc + acc_val
            return total_loss, total_acc
        else:
            raise AttributeError('Unsupported loss type!')