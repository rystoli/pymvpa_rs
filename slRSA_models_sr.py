from mvpa2.suite import *
import os
import pylab as pylab
import numpy as np
import rsa as rsa
from scipy.spatial.distance import pdist, squareform
import pcorr #for partial rsa

##################################################
# currently in progress of making this module with slRSA functions...

# TO DO: 

#*****   allow slRSA functions kwargs to use overlap_mgs instead of default mgs; issue may be that overlap_msg() requires omit submitted directly to it? nope, not issue just need to include?

#move dataloading etc. to end in __main__; make dsms refresh take arguments

# allow people to not use 'omit' argument

##################################################

def countDig(dig,arr):
    '''Counts value 'dig' in 1D iterable arr'''
    count = 0
    for i in arr:
        if i==dig: count+=1
    return count

##################################################
# data/dsm prep
##################################################

def dsms_refresh():
    '''
    Refreshes hdf5 file with dsms from srmtfmri_dsms.py B
    '''
    import srmtfmri_dsms
    dsms_fc={'apriori': srmtfmri_dsms.apriori, 'sexIdio': srmtfmri_dsms.sexIdio, 'raceIdio': srmtfmri_dsms.raceIdio, 'colorIdio': srmtfmri_dsms.colorIdio, 'sexIdioAvg': srmtfmri_dsms.idioAvg_sr['sex'], 'raceIdioAvg': srmtfmri_dsms.idioAvg_sr['race'], 'colorIdioAvg': srmtfmri_dsms.idioAvg_sr['color']}
    h5save('dsms_sr.hdf5',dsms_fc,compression=9)
    return h5load(os.path.join(homedir,dsmspath))

def overlap_mgs(ds,mgslist,omit):
    '''
    Returns pyMVPA dataset where samples are mean neural patterns per target category, where target categories can overlap - e.g., male=whitemale+blackmale, white=whitemale+whitefemale, etc.
    
    ds: single pymvpa dataset with targets already defined, and additional sample attributes identifying higher level target group memberships (eg, where 'target'=whitemale, 'sex'=male & 'race'=white
    mgslist: list of sample attribute names for higher level target groups (those which overlap
    omit: list of targets to be omitted from analyses
    
    NOTE: assumes mgs puts things in alphabetical order...
    '''

    #omissions
    for om in omit:
        ds = ds[ds.sa.targets != om] # cut out omits
        print('Target |%s| omitted from analysis' % (om))

    #create mean neural pattern per new target
    premerge = {} # list of mgs results to be merged into new ds
    for mgs in mgslist:
        premerge[mgs] = mean_group_sample([mgs])(ds)
        premerge[mgs].sa['targets'] = np.unique(premerge[mgs].sa[mgs]) #set correct targets

    nds = vstack(premerge.values()) #new dataset
    return mean_group_sample(['targets'])(nds)

def clust2mask(clusts_infile, clustkeys, savenifti = False, outprefix = ''):
    '''
    Returns dict of cluster maks arrays per specified clusters/indices via afni cluster output; can also save these as separate nifti files to be used with fmri_dataset

    clusts_infile = name of nifti file from afni where each cluster is saved as unique integer
    clustkeys: dict of clusters to be separated out and saved, where keys are indices and values are names of ROIs (used in filenaming)
    savenifti: default False, saves each clustmask as separate nifti file
    outprefix: prefix for outfile name
    '''

    clusts = fmri_dataset(clusts_infile)
    clustmasks = {}
    for i,clust in clustkeys.iteritems():
        clustmasks[clust] = clusts.samples[0] == i
        if savenifti == True: slRSA2nifti(clusts.samples[0]==i,clusts,'%s%s.nii.gz' % (outprefix,clust))
    return clustmasks

###############################################
# Data output functions
###############################################

#remap slRSA results array to native space and save to nifti
def slRSA2nifti(ds,remap,outfile):
    '''
    No return; converts slRSA output and saves nifti file to working directory

    ds=array of slRSA results
    remap: dataset to remap to
    outfile: string outfile name including extension .nii.gz
    '''

    nimg = map2nifti(data=ds,dataset=remap)
    nimg.to_filename(outfile)

def datadict2nifti(datadict,remap,outdir,outprefix=''):
    '''

    No return; runs slRSA2nifti on dictionary of slRSA data files (1subbrick), saving each file based upon its dict key

    datadict: dictionary of pymvpa datasets
    remap: dataset to remap to
    outdir: target directory to save nifti output
    outprefix: optional; prefix string to outfile name

    TO DO: make call afni for 3ddtest...
    '''

    os.mkdir(outdir) #make directory to store data
    for key,ds in datadict.iteritems():
        print('Writing nifti for subject: %s' % (key))
        slRSA2nifti(ds,remap,os.path.join(outdir,'%s%s.nii.gz' % (outprefix,key)))
        print('NIfTI successfully saved: %s' % (os.path.join(outdir,'%s%s.nii.gz' % (outprefix,key))))

def ndsmROI(ds,cmaskfile,omit,cmaskmaskfile=None,dsm2csv=False,csvname=None,mgslist=None):
    '''
    Returns neural DSM of ROI specified via mask file
    
    ds: pymvpa dataset
    cmaskfile: nifti filename of ROI mask
    omit: targets to be omitted from DSM
    cmaskmaskfile: mask to be applied to ROI mask to make same size as neural ds; default None
    dsm2csv: saves dsm as csv if True; default False
    csvname: outfile name for csv; defualt None
    mgslist: if want to use overlap_mgs, set list here
    '''

    cmask = fmri_dataset(cmaskfile,mask=cmaskmaskfile)
    ds_masked = ds
    ds_masked.samples *= cmask.samples
    ds_masked = remove_invariant_features(ds_masked)
    for om in omit:
        ds_masked = ds_masked[ds_masked.sa.targets != om] # cut out omits
        print('Target |%s| omitted from analysis' % (om))
    if mgslist == None: ds_maskedUT = mean_group_sample(['targets'])(ds_masked) #make UT ds
    elif mgslist != None:
        print('overlap used instead')
        ds_maskedUT = overlap_mgs(ds_masked,mgslist,omit)
    print('shape:',ds_maskedUT.shape)
    ndsm = squareform(pdist(ds_maskedUT.samples,'correlation'))
    if dsm2csv == True: np.savetxt(csvname, ndsm, delimiter = ",")
    return ndsm

def roi2ndsm_nSs(data, cmaskfiles, omit, mask, h5=0, h5name = 'ndsms_persubj.hdf5',mgslist=None):
    '''
    Runs ndsmROI on data dictionary of subjects, for each ROI maskfile specified

    data: datadict, keys subjids, values pymvpa dsets
    cmaskfiles: list of cluster mask ROI file names +.nii.gz
    omit: targets omitted
    mask: mask filename +.nii.gz to equate datasets
    h5: 1 saves full dict of dsms per ROI per subj as hdf5, default 0
    h5name: name for hdf5
    mgslist: if want to use overlap_mgs, set list here

    to do: make call of ndsmROI more flexible
    '''

    data = h5load(os.path.join(homedir,dpath))
    ndsms_persubj = {}
    for ds in data:
        ndsms_persubj[ds]={}
        print('Starting ndsms for subj: %s' % (ds))
        for cmfile in cmaskfiles:
            temp_ds = data[ds].copy()
            ndsms_persubj[ds][cmfile] = ndsmROI(temp_ds,cmfile,['omnF','pro'],mask,dsm2csv=True,csvname='%s_%s.csv' % (ds,cmfile),mgslist=mgslist)
            print('ndsm added to dict and saved as %s_%s.csv' % (ds,cmfile))
    if h5==1: h5save('ndsms_persubj.hdf5',ndsms_persubj,compression=9)
    return ndsms_persubj

def avg_ndsms(ndsms,cmaskfiles,h5=0,h5fname='avg_nDSMs.hdf5',savecsv=0):
    '''
    Returns dict of average nDSM per ROI in output of roi2ndsm_nSs - cmaskfiles - list of cmaksfiles
    '''
    avg_ndsms = dict([(cmask,np.mean([ndsms[subj][cmask] for subj in ndsms],axis=0)) for cmask in cmaskfiles])
    if h5==1: h5save(h5fname,avg_ndsms,compression=9)
    for dsm in avg_ndsms:
        if savecsv == 1: np.savetxt('%s_avg_ndsm.csv' % (dsm), avg_ndsms[dsm], delimiter = ",")
    return avg_ndsms

###############################################
# Runs slRSA with defined model for 1 subject
###############################################

def slRSA_m_1Ss(ds, model, omit, partial_dsm = None, radius=3, cmetric='pearson'):
    '''one subject

    Executes slRSA on single subjects and returns tuple of arrays of 1-p's [0], and fisher Z transformed r's [1]

    ds: pymvpa dsets for 1 subj
    model: model DSM to be correlated with neural DSMs per searchlight center
    partial_dsm: model DSM to be partialled out of model-neural DSM correlation
    omit: list of targets omitted from pymvpa datasets
    radius: sl radius, default 3
    cmetric: default pearson, other optin 'spearman'
    '''        

    if __debug__:
        debug.active += ["SLC"]

    for om in omit:
        ds = ds[ds.sa.targets != om] # cut out omits
        print('Target |%s| omitted from analysis' % (om))
    ds = mean_group_sample(['targets'])(ds) #make UT ds
    print('Mean group sample computed at size:',ds.shape,'...with UT:',ds.UT)

    print('Beginning slRSA analysis...')
    if partial_dsm == None: tdcm = rsa.TargetDissimilarityCorrelationMeasure(squareform(model), comparison_metric=cmetric)
    elif partial_dsm != None: tdcm = rsa.TargetDissimilarityCorrelationMeasure(squareform(model), comparison_metric=cmetric, partial_dsm = squareform(partial_dsm))
    sl = sphere_searchlight(tdcm,radius=radius)
    slmap = sl(ds)
    if partial_dsm == None:
        print('slRSA complete with map of shape:',slmap.shape,'...p max/min:',slmap.samples[0].max(),slmap.samples[0].min(),'...r max/min',slmap.samples[1].max(),slmap.samples[1].min())
        return 1-slmap.samples[1],np.arctanh(slmap.samples[0])
    else:
        print('slRSA complete with map of shape:',slmap.shape,'...r max/min:',slmap.samples[0].max(),slmap.samples[0].min())
        return np.arctanh(slmap.samples[0])
    

###############################################
# Runs group level slRSA with defined model
###############################################

def slRSA_m_nSs(data, model, omit, radius=3, partial_dsm = None, cmetric = 'pearson', h5 = 0, h5out = 'slRSA_m_nSs.hdf5'):
    '''

    Executes slRSA per subject in datadict (keys=subjIDs), returns dict of avg map fisher Z transformed r's and 1-p's per voxel arrays

    data: dictionary of pymvpa dsets per subj, indices being subjIDs
    model: model DSM to be correlated with neural DSMs per searchlight center
    partial_dsm: model DSM to be partialled out of model-neural DSM correlation
    omit: list of targets omitted from pymvpa datasets
    radius: sl radius, default 3
    cmetric: default pearson, other optin 'spearman'
    h5: 1 if you want to save hdf5 as well
    h5out: hdf5 outfilename
    '''        
    
    print('Model slRSA initiated with...\n Ss: %s\nmodel shape: %s\nomitting: %s\nradius: %s\nh5: %s\nh5out: %s' % (data.keys(),model.shape,omit,radius,h5,h5out))

    ### slRSA per subject ###
    slr={'p': {}, 'r':{}} #dictionary to hold fzt r's and 1-p's
    print('Beginning group level searchlight on %s Ss...' % (len(data)))
    for subjid,ds in data.iteritems():
        print('\nPreparing slRSA for subject %s' % (subjid))
        subj_data = slRSA_m_1Ss(ds,model,omit,partial_dsm=partial_dsm,cmetric=cmetric)
        if partial_dsm == None: slr['p'][subjid],slr['r'][subjid] = subj_data[0],subj_data[1]
        else: slr['r'][subjid] = subj_data
    print('slRSA complete for all subjects')

    if h5==1:
        h5save(h5out,slr,compression=9)
        return slr
    else: return slr
    

###############################################
# across subjects RSA
###############################################

def slRSA_xSs(data,omit,measure='DCM',radius=3,h5=0,h5out='slRSA_xSs.hdf5'):
    '''
    
    Returns avg map of xSs correlations of neural DSMs per searchlight sphere center
    - uses either Dissimilarity Consistency Measure or RSMMeasure, recommended DCM, as of now RSM seems unusual

    data: dictionary of pymvpa dsets per subj, indices being subjIDs
    omit: list of targets omitted from pymvpa datasets
    radius: sl radius, default 3
    measure: specify if measure is 'DCM' or 'RSM'
    h5: 1 saves hdf5 of output as well 
    h5out: hdf5 outfilename
    
    TO DO: should not return average, but full ds of pairs? - need to split ds's into different keys in datadict
    '''   

    print('%s xSs slRSA initiated with...\n Ss: %s\nomitting: %s\nradius: %s\nh5: %s\nh5out: %s' % (measure,data.keys(),omit,radius,h5,h5out))

    if __debug__:
        debug.active += ["SLC"]
    
    for i in data:
        data[i] = mean_group_sample(['targets'])(data[i]) 
    print('Dataset targets averaged with shapes:',[ds.shape for ds in data.values()])

    #omissions
    print('Omitting targets: %s from data' % (omit))
    for i in data:
        for om in omit:
            data[i] = data[i][data[i].sa.targets != om]

    if measure=='DCM':
        group_data = None
        for s in data.keys():
             ds = data[s]
             ds.sa['chunks'] = [s]*len(ds)
             if group_data is None: group_data = ds
             else: group_data.append(ds)
        print('Group dataset ready including Ss: %s\nBeginning slRSA:' % (np.unique(group_data.chunks)))
        dcm = rsa.DissimilarityConsistencyMeasure()
        sl_dcm = sphere_searchlight(dcm,radius=radius)
        slmap_dcm = sl_dcm(group_data)
        print('Analysis complete with shape:',slmap_dcm.shape)
        if h5 == 1:
            h5save(h5out,slmap_dcm,compression=9)
            return slmap_dcm
        else: return slmap_dcm

####################################
#  Setup - will delete this later, but good for texting
####################################
homedir = '/home/freeman_lab/fMRI/Stolier/SRMTfMRI'
dpath = 'prep/standard_13.11/'
maskpath = 'masks/avg_mask_d3_BEST.nii.gz'
dsmspath= 'analysis/dsms_sr.hdf5'
remappath = 'analysis/data_remap_159.nii.gz'

#load data
sexdata = h5load(os.path.join(homedir,dpath,'srmtfmri_sex.gzipped.hdf5'))
racedata = h5load(os.path.join(homedir,dpath,'srmtfmri_race.gzipped.hdf5'))
colordata = h5load(os.path.join(homedir,dpath,'srmtfmri_color.gzipped.hdf5'))
print('\nLoading data from %s ...' % (os.path.join(homedir,dpath)))
print('Sex task:')
for ds in sexdata:
    print('Subj %s ; shape:' % (ds), sexdata[ds].shape)
print('Race task:')
for ds in racedata:
    print('Subj %s ; shape:' % (ds), racedata[ds].shape)
print('Color task:')
for ds in colordata:
    print('Subj %s ; shape:' % (ds), colordata[ds].shape)

#load remap ds
remap = fmri_dataset(os.path.join(homedir,remappath),mask=os.path.join(homedir,maskpath))
print('Remap dataset loaded from %s, with shape:' % (os.path.join(homedir,remappath)),remap.shape)

dsms = dsms_refresh()

print('\nAnalysis materials successfully loaded')
