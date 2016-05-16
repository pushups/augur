from __future__ import division, print_function
import numpy as np
import time
from collections import defaultdict
from nextstrain.io_util import myopen
from itertools import izip
import pandas as pd


class titers(object):
    '''
    this class decorates as phylogenetic tree with titer measurements and infers
    different models that describe titer differences in a parsimonious way.
    Two additive models are currently implemented, the tree and the subsitution
    model. The tree model describes titer drops as a sum of terms associated with
    branches in the tree, while the substitution model attributes titer drops to amino
    acid mutations. More details on the methods can be found in
    Neher et al, PNAS, 2016
    '''

    def __init__(self, tree, titer_fname = 'data/HI_titers.txt', **kwargs):
        self.kwargs = kwargs
        # set self.tree and dress tree with a number of extra attributes
        self.prepare_tree(tree)

        # read the titers and assign to self.titers, in addition
        # self.strains and self.sources are assigned
        self.read_titers(titer_fname)


    def prepare_tree(self, tree):
        self.tree = tree # not copied, just linked
        # produce dictionaries that map node names to nodes regardless of capitalization
        self.node_lookup = {n.name:n for n in tree.get_terminals()}
        self.node_lookup.update({n.name.upper():n for n in tree.get_terminals()})
        self.node_lookup.update({n.name.lower():n for n in tree.get_terminals()})

        # have each node link to its parent. this will be needed for walking up and down the tree
        self.tree.root.parent_node=None
        for node in self.tree.get_nonterminals():
            for c in node.clades:
                c.parent_node = node


    def read_titers(self, fname):
        self.titer_fname = fname
        if "excluded_tables" in self.kwargs:
            self.excluded_tables = self.kwargs["excluded_tables"]
        else:
            self.excluded_tables = []

        strains = set()
        measurements = defaultdict(list)
        sources = set()
        with myopen(fname, 'r') as infile:
            for line in infile:
                entries = line.strip().split()
                test, ref_virus, serum, src_id, val = (entries[0], entries[1],entries[2],
                                                        entries[3], float(entries[4]))
                ref = (ref_virus, serum)
                if src_id not in self.excluded_tables:
                    try:
                        measurements[(test, (ref_virus, serum))].append(val)
                        strains.update([test, ref])
                        sources.add(src_id)
                    except:
                        print(line.strip())
        self.titers = measurements
        self.strains = list(strains)
        self.sources = list(sources)


    def normalize(self, ref, val):
        consensus_func = np.mean
        return consensus_func(np.log2(self.autologous_titers[ref]['val'])) \
                - consensus_func(np.log2(val))

    def determine_autologous_titers(self):
        autologous = defaultdict(list)
        all_titers_per_serum = defaultdict(list)
        for (test, ref), val in self.titers.iteritems():
            if ref[0].upper() in self.node_lookup:
                all_titers_per_serum[ref].append(val)
                if ref[0]==test:
                    autologous[ref].append(val)

        self.autologous_titers = {}
        for serum in all_per_serum:
            if serum in autologous:
                self.autologous_titers[serum] = {'val':autologous[serum], 'autologous':True}
                print("autologous titer found for",serum)
            else:
                if len(all_per_serum[serum])>10:
                    self.autologous_titers[serum] = {'val':np.max(all_per_serum[serum]),
                                                     'autologous':False}
                    print(serum,": using max titer instead of autologous,",
                          np.max(all_per_serum[serum]))
                else:
                    print("discarding",serum,"since there are only ",
                           len(all_per_serum[serum]),'measurements')


    def normalize_titers(self):
        '''
        convert the titer measurements into the log2 difference between the average
        titer measured between test virus and reference serum and the average
        homologous titer. all measurements relative to sera without homologous titer
        are excluded
        '''
        self.determine_autologous_titers()

        self.titers_normalized = {}
        self.consensus_titers_raw = {}
        self.measurements_per_serum = defaultdict(int)

        for (test, ref), val in self.titers.iteritems():
            if test.upper() in self.node_lookup and ref[0].upper() in self.node_lookup:
                if ref in self.autologous_titers: # use only titers for which estimates of the autologous titer exists
                    test_strains.add(test.upper())
                    test_strains.add(ref[0].upper())
                    sera.add(ref)
                    ref_strains.add(ref[0])
                    self.titers_normalized[(test, ref)] = self.normalize(ref, val)
                    self.consensus_titers_raw[(test, ref)] = np.median(val)
                    self.measurements_per_serum[ref]+=1
                else:
                    pass
                    #print "no homologous titer found:", ref

        self.sera = list(sera)
        self.ref_strains = list(ref_strains)
        self.test_strains = list(test_strains)


    def make_training_set(self, date_range=None, training_fraction=1.0, subset_strains=False):
        if self.training_fraction<1.0: # validation mode, set aside a fraction of measurements to validate the fit
            self.test_titers, self.train_titers = {}, {}
            if subset_strains:    # exclude a fraction of test viruses as opposed to a fraction of the titers
                tmp = set(self.test_strains)
                tmp.difference_update(self.ref_strains) # don't use references viruses in the set to sample from
                training_strains = sample(tmp, int(self.training_fraction*len(tmp)))
                for tmpstrain in self.ref_strains:      # add all reference viruses to the training set
                    if tmpstrain not in training_strains:
                        training_strains.append(tmpstrain)
                for key, val in self.titers_normalized.iteritems():
                    if key[0] in training_strains:
                        self.train_titers[key]=val
                    else:
                        self.test_titers[key]=val
            else: # simply use a fraction of all measurements for testing
                for key, val in self.titers_normalized.iteritems():
                    if np.random.uniform()>self.training_fraction:
                        self.test_titers[key]=val
                    else:
                        self.train_titers[key]=val
        else: # without the need for a test data set, use the entire data set for training
            self.train_titers = self.titers_normalized

        # if data is to censored by date, subset the data set and reassign sera, reference strains, and test viruses
        if self.date_range is not None:
            prev_years = 6 # number of years prior to cut-off to use when fitting date censored data
            self.train_titers = {key:val for key,val in self.train_HI.iteritems()
                                if self.node_lookup[key[0]].num_date<=self.date_range[0] and
                                   self.node_lookup[key[1][0]].num_date<=self.date_range[0] and
                                   self.node_lookup[key[0]].num_date>self.date_range[1] and
                                   self.node_lookup[key[1][0]].num_date>self.date_range[1]}
            sera = set()
            ref_strains = set()
            test_strains = set()

            for test,ref in self.train_HI:
                if test.upper() in self.node_lookup and ref[0].upper() in self.node_lookup:
                    test_strains.add(test)
                    test_strains.add(ref[0])
                    sera.add(ref)
                    ref_strains.add(ref[0])

            self.sera = list(sera)
            self.ref_strains = list(ref_strains)
            self.test_strains = list(HI_strains)

    def train(self, method='nnl1reg',  lam_drop=1.0, lam_pot = 0.5, lam_avi = 3.0):
        '''
        determine the model parameters -- lam_drop, lam_pot, lam_avi are
        the regularization parameters.
        '''
        self.lam_pot = lam_pot
        self.lam_avi = lam_avi
        self.lam_drop = lam_drop

        if method=='l1reg':  # l1 regularized fit, no constraint on sign of effect
            self.model_params = self.fit_l1reg()
        elif method=='nnls':  # non-negative least square, not regularized
            self.model_params = self.fit_nnls()
        elif method=='nnl2reg': # non-negative L2 norm regularized fit
            self.model_params = self.fit_nnl2reg()
        elif method=='nnl1reg':  # non-negative fit, branch terms L1 regularized, avidity terms L2 regularized
            self.model_params = self.fit_nnl1reg()

        print('rms deviation on training set=',np.sqrt(self.fit_func()))

        self.serum_potency = {serum:self.params[self.genetic_params+ii]
                              for ii, serum in enumerate(self.sera)}
        self.virus_effect = {strain:self.params[self.genetic_params+len(self.sera)+ii]
                             for ii, strain in enumerate(self.HI_strains)}


    def fit_func(self):
        return np.mean( (self.titer_dist - np.dot(self.design_matrix, self.model_params))**2 )

    ###
    # define fitting routines for different objective functions
    ###
    def fit_l1reg(self):
        '''
        regularize genetic parameters with an l1 norm regardless of sign
        '''
        from cvxopt import matrix, solvers
        n_params = self.design_matrix.shape[1]
        n_genetic = self.genetic_params
        n_sera = len(self.sera)
        n_v = len(self.HI_strains)

        # set up the quadratic matrix containing the deviation term (linear xterm below)
        # and the l2-regulatization of the avidities and potencies
        P1 = np.zeros((n_params+n_genetic,n_params+n_genetic))
        P1[:n_params, :n_params] = self.TgT
        for ii in xrange(n_genetic, n_genetic+n_sera):
            P1[ii,ii]+=self.lam_pot
        for ii in xrange(n_genetic+n_sera, n_params):
            P1[ii,ii]+=self.lam_avi
        P = matrix(P1)

        # set up cost for auxillary parameter and the linear cross-term
        q1 = np.zeros(n_params+n_genetic)
        q1[:n_params] = -np.dot( self.titer_dist, self.design_matrix)
        q1[n_params:] = self.lam_drop
        q = matrix(q1)

        # set up linear constraint matrix to regularize the HI parametesr
        h = matrix(np.zeros(2*n_genetic))   # Gw <=h
        G1 = np.zeros((2*n_genetic,n_params+n_genetic))
        G1[:n_genetic, :n_genetic] = -np.eye(n_genetic)
        G1[:n_genetic:, n_params:] = -np.eye(n_genetic)
        G1[n_genetic:, :n_genetic] = np.eye(n_genetic)
        G1[n_genetic:, n_params:] = -np.eye(n_genetic)
        G = matrix(G1)
        W = solvers.qp(P,q,G,h)
        return np.array([x for x in W['x']])[:n_params]


    def fit_nnls(self):
        from scipy.optimize import nnls
        return nnls(self.design_matrix, self.titer_dist)[0]


    def fit_nnl2reg(self):
        from cvxopt import matrix, solvers
        n_params = self.design_matrix.shape[1]
        P = matrix(np.dot(self.design_matrix.T, self.design_matrix) + self.lam_drop*np.eye(n_params))
        q = matrix( -np.dot( self.titer_dist, self.design_matrix))
        h = matrix(np.zeros(n_params)) # Gw <=h
        G = matrix(-np.eye(n_params))
        W = solvers.qp(P,q,G,h)
        return np.array([x for x in W['x']])


    def fit_nnl1reg(self):
        ''' l1 regularization of titer drops with non-negativity constraints'''
        from cvxopt import matrix, solvers
        n_params = self.design_matrix.shape[1]
        n_genetic = self.genetic_params
        n_sera = len(self.sera)
        n_v = len(self.HI_strains)

        # set up the quadratic matrix containing the deviation term (linear xterm below)
        # and the l2-regulatization of the avidities and potencies
        P1 = np.zeros((n_params,n_params))
        P1[:n_params, :n_params] = self.TgT
        for ii in xrange(n_genetic, n_genetic+n_sera):
            P1[ii,ii]+=self.lam_pot
        for ii in xrange(n_genetic+n_sera, n_params):
            P1[ii,ii]+=self.lam_avi
        P = matrix(P1)

        # set up cost for auxillary parameter and the linear cross-term
        q1 = np.zeros(n_params)
        q1[:n_params] = -np.dot(self.titer_dist, self.design_matrix)
        q1[:n_genetic] += self.lam_drop
        q = matrix(q1)

        # set up linear constraint matrix to enforce positivity of the
        # dTiters and bounding of dTiter by the auxillary parameter
        h = matrix(np.zeros(n_genetic))     # Gw <=h
        G1 = np.zeros((n_genetic,n_params))
        G1[:n_genetic, :n_genetic] = -np.eye(n_genetic)
        G = matrix(G1)
        W = solvers.qp(P,q,G,h)
        return = np.array([x for x in W['x']])[:n_params]


class tree_model(titers):
    """docstring for tree_model"""
    def __init__(self, **kwargs):
        super(tree_model, self).__init__(**kwargs)

    def prepare(self, **kwargs):
        self.make_training_set(**kwargs)
        self.find_titer_splits()
        self.make_treegraph()

    def get_path_no_terminals(self, v1, v2):
        '''
        returns the path between two tips in the tree excluding the terminal branches.
        '''
        if v1 in self.node_lookup and v2 in self.node_lookup:
            p1 = [self.node_lookup[v1]]
            p2 = [self.node_lookup[v2]]
            for tmp_p in [p1,p2]:
                while tmp_p[-1].parent_node != self.tree.root:
                    tmp_p.append(tmp_p[-1].parent_node)
                tmp_p.append(self.tree.root)
                tmp_p.reverse()

            for pi, (tmp_v1, tmp_v2) in enumerate(izip(p1,p2)):
                if tmp_v1!=tmp_v2:
                    break
            path = [n for n in p1[pi:] if n.titer_info>1] + [n for n in p2[pi:] if n.titer_info>1]
        else:
            path = None
        return path


    def find_titer_splits(self, criterium=None):
        '''
        walk through the tree, mark all branches that are to be included as model variables
         - no terminals
        '''
        if criterium is None:
            criterium = lambda x:True
        # flag all branches on the tree with titer_info = True if they lead to strain with titer data
        for leaf in self.tree.get_terminals():
            if leaf.strain.upper() in self.test_strains:
                leaf.serum = leaf.strain.upper() in self.ref_strains
                leaf.titer_info = 1
            else:
                leaf.serum, leaf.titer_info=False, 0

        for node in self.tree.get_nonterminals(order='postorder'):
            node.titer_info = sum([c.titer_info for c in node.clades])
            node.serum= False

        # combine sets of branches that span identical sets of titers
        self.titer_split_count = 0  # titer split counter
        self.titer_split_to_branch = defaultdict(list)
        for node in self.tree.find_clades(order='preorder'):
            node.dTiter, node.cTiter, node.constraints = 0, 0, 0
            if node.titer_info>1 and criterium(node):
                node.titer_branch_index = self.titer_split_count
                self.titer_split_to_branch[node.titer_branch_index].append(node)
                # at a bi- or multifurcation, increase the split count and HI index
                # either individual child branches have enough HI info be counted,
                # or the pre-order node iteraction will move towards the root
                if sum([c.titer_info>0 for c in node.clades])>1:
                    self.titer_split_count+=1
                elif node.is_terminal():
                    self.titer_split_count+=1
            else:
                node.titer_branch_index=None

        print ("# of reference strains:",len(self.sera),
               "# of branches with HI constraint", self.titer_split_count)


    def make_treegraph(self):
        '''
        code the path between serum and test virus of each HI measurement into a matrix
        the matrix has dimensions #measurements x #tree branches with HI info
        if the path between test and serum goes through a branch,
        the corresponding matrix element is 1, 0 otherwise
        '''
        tree_graph = []
        titer_dist = []
        weights = []
        # mark HI splits have to have been run before, assigning self.titer_split_count
        n_params = self.titer_split_count + len(self.sera) + len(self.test_strains)
        for (test, ref), val in self.train_HI.iteritems():
            if not np.isnan(val):
                try:
                    if ref[0] in self.node_lookup and test in self.node_lookup:
                        path = self.get_path_no_terminals(test, ref[0])
                        tmp = np.zeros(n_params, dtype=int)
                        # determine branch indices on path
                        branches = np.unique([c.titer_branch_index for c in path
                                                 if c.titer_branch_index is not None])

                        if len(branches): tmp[branches] = 1
                        # add serum effect for heterologous viruses
                        if ref[0]!=test:
                            tmp[self.titer_split_count+self.sera.index(ref)] = 1
                        # add virus effect
                        tmp[self.titer_split_count+len(self.sera)+self.test_strains.index(test)] = 1
                        # append model and fit value to lists tree_graph and titer_dist
                        tree_graph.append(tmp)
                        titer_dist.append(val)
                        weights.append(1.0/(1.0 + self.serum_Kc*self.measurements_per_serum[ref]))
                except:
                    import ipdb; ipdb.set_trace()
                    print test, ref, "ERROR"

        # convert to numpy arrays and save product of tree graph with its transpose for future use
        self.weights = np.sqrt(weights)
        self.titer_dist =  np.array(titer_dist)*self.weights
        self.design_matrix = (np.array(tree_graph).T*self.weights).T
        self.TgT = np.dot(self.design_matrix.T, self.design_matrix)
        print ("Found", self.design_matrix.shape, "measurements x parameters")

    def train_tree(self,**kwargs):
        self.train(**kwargs)
        for node in self.tree.find_clades(order='postorder'):
            node.dTiter=0
        for HI_split, branches in self.HI_split_to_branch.iteritems():
            likely_branch = branches[np.argmax([b.n_aa_muts for b in branches])]
            likely_branch.dTiter = self.model_params[HI_split]
            likely_branch.constraints = self.tree_graph[:,HI_split].sum()

        # integrate the tree model dTiter into a cumulative antigentic evolution score cTiter
        for node in self.tree.find_clades(order='preorder'):
            if node.parent_node is not None:
                node.cTiter = node.parent_node.cTiter + node.dTiter
            else:
                node.cTiter=0

    def predict_titer(self, virus, serum, cutoff=0.0):
        path = self.get_path_no_terminals(virus,serum[0])
        if path is not None:
            return self.serum_potency[serum] \
                    + self.virus_effect[virus] \
                    + np.sum([b.dTiter for b in path if b.dTiter>cutoff])
        else:
            return None


if __name__=="__main__":
    pass
