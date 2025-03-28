#!/usr/local/miniconda/bin/python
import argparse
import os
import shutil
import nibabel
from glob import glob
from subprocess import Popen, PIPE
from shutil import rmtree
import subprocess
from bids.layout import BIDSLayout
from bids.layout.models import *
from functools import partial
from collections import OrderedDict
from pathlib import Path
import numpy as np

def run(command, env={}, cwd=None):
    merged_env = os.environ
    merged_env.update(env)
    merged_env.pop("DEBUG", None)
    print(command)
    process = Popen(command, stdout=PIPE, stderr=subprocess.STDOUT,
                    shell=True, env=merged_env, cwd=cwd,
                    universal_newlines=True)
    while True:
        line = process.stdout.readline()
        print(line.rstrip())
        line = str(line)[:-1]
        if line == '' and process.poll() != None:
            break
    if process.returncode != 0:
        raise Exception("Non zero return code: %d"%process.returncode)

grayordinatesres = "2" # This is currently the only option for which the is an atlas
lowresmesh = 32

def run_pre_freesurfer(**args):
    args.update(os.environ)
    args["t1"] = "@".join(t1ws)
    if t2ws != "NONE":
        args["t2"] = "@".join(t2ws)
    else:
        args["t2"] = "NONE"
        args["t2_template_res"] = args["t1_template_res"]

    cmd = '{HCPPIPEDIR}/PreFreeSurfer/PreFreeSurferPipeline.sh ' + \
    '--path="{path}" ' + \
    '--subject="{subject}" ' + \
    '--t1="{t1}" ' + \
    '--t2="{t2}" ' + \
    '--t1template="{HCPPIPEDIR_Templates}/MNI152_T1_{t1_template_res}mm.nii.gz" ' + \
    '--t1templatebrain="{HCPPIPEDIR_Templates}/MNI152_T1_{t1_template_res}mm_brain.nii.gz" ' + \
    '--t1template2mm="{HCPPIPEDIR_Templates}/MNI152_T1_2mm.nii.gz" ' + \
    '--t2template="{HCPPIPEDIR_Templates}/MNI152_T2_{t2_template_res}mm.nii.gz" ' + \
    '--t2templatebrain="{HCPPIPEDIR_Templates}/MNI152_T2_{t2_template_res}mm_brain.nii.gz" ' + \
    '--t2template2mm="{HCPPIPEDIR_Templates}/MNI152_T2_2mm.nii.gz" ' + \
    '--t2samplespacing="{t2samplespacing}" ' + \
    '--templatemask="{HCPPIPEDIR_Templates}/MNI152_T1_{t1_template_res}mm_brain_mask.nii.gz" ' + \
    '--template2mmmask="{HCPPIPEDIR_Templates}/MNI152_T1_2mm_brain_mask_dil.nii.gz" ' + \
    '--brainsize="150" ' + \
    '--fnirtconfig="{HCPPIPEDIR_Config}/T1_2_MNI152_2mm.cnf" ' + \
    '--fmapmag="{fmapmag}" ' + \
    '--fmapphase="{fmapphase}" ' + \
    '--fmapgeneralelectric="NONE" ' + \
    '--echodiff="{echodiff}" ' + \
    '--SEPhaseNeg="{SEPhaseNeg}" ' + \
    '--SEPhasePos="{SEPhasePos}" ' + \
    '--seechospacing="{echospacing}" ' + \
    '--seunwarpdir="{seunwarpdir}" ' + \
    '--t1samplespacing="{t1samplespacing}" ' + \
    '--unwarpdir="{unwarpdir}" ' + \
    '--gdcoeffs={gdcoeffs} ' + \
    '--avgrdcmethod={avgrdcmethod} ' + \
    '--topupconfig="{HCPPIPEDIR_Config}/b02b0.cnf" ' + \
    '--processing-mode="{processing_mode}" ' + \
    '--printcom=""'
    cmd = cmd.format(**args)
    run(cmd, cwd=args["path"], env={"OMP_NUM_THREADS": str(args["n_cpus"])})

def run_freesurfer(**args):
    args.update(os.environ)
    args["subjectDIR"] = os.path.join(args["path"], args["subject"], "T1w")
    cmd = '{HCPPIPEDIR}/FreeSurfer/FreeSurferPipeline.sh ' + \
      '--subject="{subject}" ' + \
      '--subjectDIR="{subjectDIR}" ' + \
      '--t1="{path}/{subject}/T1w/T1w_acpc_dc_restore.nii.gz" ' + \
      '--t1brain="{path}/{subject}/T1w/T1w_acpc_dc_restore_brain.nii.gz" ' + \
      '--processing-mode="{processing_mode}" '
    if args["processing_mode"] != "LegacyStyleData":
        cmd = cmd + '--t2="{path}/{subject}/T1w/T2w_acpc_dc_restore.nii.gz" '
    cmd = cmd.format(**args)

    if not os.path.exists(os.path.join(args["subjectDIR"], "fsaverage")):
        shutil.copytree(os.path.join(os.environ["SUBJECTS_DIR"], "fsaverage"),
                        os.path.join(args["subjectDIR"], "fsaverage"))
    if not os.path.exists(os.path.join(args["subjectDIR"], "lh.EC_average")):
        shutil.copytree(os.path.join(os.environ["SUBJECTS_DIR"], "lh.EC_average"),
                        os.path.join(args["subjectDIR"], "lh.EC_average"))
    if not os.path.exists(os.path.join(args["subjectDIR"], "rh.EC_average")):
        shutil.copytree(os.path.join(os.environ["SUBJECTS_DIR"], "rh.EC_average"),
                        os.path.join(args["subjectDIR"], "rh.EC_average"))

    run(cmd, cwd=args["path"], env={"NSLOTS": str(args["n_cpus"]),
                                    "OMP_NUM_THREADS": str(args["n_cpus"])})

def run_post_freesurfer(**args):
    args.update(os.environ)
    cmd = '{HCPPIPEDIR}/PostFreeSurfer/PostFreeSurferPipeline.sh ' + \
      '--path="{path}" ' + \
      '--subject="{subject}" ' + \
      '--surfatlasdir="{HCPPIPEDIR_Templates}/standard_mesh_atlases" ' + \
      '--grayordinatesdir="{HCPPIPEDIR_Templates}/91282_Greyordinates" ' + \
      '--grayordinatesres="{grayordinatesres:s}" ' + \
      '--hiresmesh="164" ' + \
      '--lowresmesh="{lowresmesh:d}" ' + \
      '--subcortgraylabels="{HCPPIPEDIR_Config}/FreeSurferSubcorticalLabelTableLut.txt" ' + \
      '--freesurferlabels="{HCPPIPEDIR_Config}/FreeSurferAllLut.txt" ' + \
      '--refmyelinmaps="{HCPPIPEDIR_Templates}/standard_mesh_atlases/Conte69.MyelinMap_BC.164k_fs_LR.dscalar.nii" ' + \
      '--regname="{regname}" ' + \
      '--processing-mode="{processing_mode}"'
    cmd = cmd.format(**args)
    run(cmd, cwd=args["path"], env={"OMP_NUM_THREADS": str(args["n_cpus"])})

def run_generic_fMRI_volume_processsing(**args):
    args.update(os.environ)
    cmd = '{HCPPIPEDIR}/fMRIVolume/GenericfMRIVolumeProcessingPipeline.sh ' + \
      '--path={path} ' + \
      '--subject={subject} ' + \
      '--fmriname={fmriname} ' + \
      '--fmritcs={fmritcs} ' + \
      '--fmriscout={fmriscout} ' + \
      '--SEPhaseNeg={SEPhaseNeg} ' + \
      '--SEPhasePos={SEPhasePos} ' + \
      '--fmapmag="NONE" ' + \
      '--fmapphase="NONE" ' + \
      '--fmapgeneralelectric="NONE" ' + \
      '--echospacing={echospacing} ' + \
      '--echodiff="NONE" ' + \
      '--unwarpdir={unwarpdir} ' + \
      '--fmrires={fmrires:s} ' + \
      '--dcmethod={dcmethod} ' + \
      '--gdcoeffs={gdcoeffs} ' + \
      '--topupconfig={HCPPIPEDIR_Config}/b02b0.cnf ' + \
      '--printcom="" ' + \
      '--biascorrection={biascorrection} ' + \
      '--mctype="MCFLIRT" ' + \
      '--processing-mode="{processing_mode}" ' + \
      '--doslicetime="{doslicetime}" ' + \
      '--slicetimerparams="{slicetimerparams}" '

    cmd = cmd.format(**args)
    run(cmd, cwd=args["path"], env={"OMP_NUM_THREADS": str(args["n_cpus"])})

def run_generic_fMRI_surface_processsing(**args):
    args.update(os.environ)
    cmd = '{HCPPIPEDIR}/fMRISurface/GenericfMRISurfaceProcessingPipeline.sh ' + \
      '--path={path} ' + \
      '--subject={subject} ' + \
      '--fmriname={fmriname} ' + \
      '--lowresmesh="{lowresmesh:d}" ' + \
      '--fmrires={fmrires:s} ' + \
      '--smoothingFWHM={fmrires:s} ' + \
      '--grayordinatesres="{grayordinatesres:s}" ' + \
      '--regname="{regname}" '
    cmd = cmd.format(**args)
    run(cmd, cwd=args["path"], env={"OMP_NUM_THREADS": str(args["n_cpus"])})

def run_diffusion_processsing(**args):
    args.update(os.environ)
    cmd = '{HCPPIPEDIR}/DiffusionPreprocessing/DiffPreprocPipeline.sh ' + \
      '--posData="{posData}" ' +\
      '--negData="{negData}" ' + \
      '--path="{path}" ' + \
      '--subject="{subject}" ' + \
      '--echospacing="{echospacing}" '+ \
      '--PEdir={PEdir} ' + \
      '--gdcoeffs={gdcoeffs} ' + \
      '--dwiname={dwiname} ' + \
      '--printcom="" '
    if args["eddy_no_gpu"]:
        cmd = cmd + ' --no-gpu '
    if args["extra_eddy_args"]:
        cmd = cmd + " ".join(["--extra-eddy-arg="+s for s in args["extra_eddy_args"].split()])
    cmd = cmd.format(**args)
    run(cmd, cwd=args["path"], env={"OMP_NUM_THREADS": str(args["n_cpus"])})

def run_diffusion_processsing_preeddy(**args):
    args.update(os.environ)
    if not "b0maxbval" in args or not args["b0maxbval"]:
        args['b0maxbval']=50
    cmd = '{HCPPIPEDIR}/DiffusionPreprocessing/DiffPreprocPipeline_PreEddy.sh ' + \
      '--posData="{posData}" ' +\
      '--negData="{negData}" ' + \
      '--path="{path}" ' + \
      '--subject="{subject}" ' + \
      '--echospacing="{echospacing}" '+ \
      '--PEdir={PEdir} ' + \
      '--dwiname={dwiname} ' + \
      '--b0maxbval={b0maxbval} ' + \
      '--printcom="" '
    cmd = cmd.format(**args)
    run(cmd, cwd=args["path"], env={"OMP_NUM_THREADS": str(args["n_cpus"])})

def run_diffusion_processsing_eddy(**args):
    args.update(os.environ)
    cmd = '{HCPPIPEDIR}/DiffusionPreprocessing/DiffPreprocPipeline_Eddy.sh ' + \
      '--path="{path}" ' + \
      '--subject="{subject}" ' + \
      '--dwiname={dwiname} ' + \
      '--printcom="" '
    if args["eddy_no_gpu"]:
        cmd = cmd + ' --no-gpu '
    if args["extra_eddy_args"]:
        cmd = cmd + " ".join(["--extra-eddy-arg="+s for s in args["extra_eddy_args"].split()])
    cmd = cmd.format(**args)
    run(cmd, cwd=args["path"], env={"OMP_NUM_THREADS": str(args["n_cpus"])})
    
def run_diffusion_processsing_posteddy(**args):
    args.update(os.environ)
    if not "dof" in args or not args["dof"]:
        args['dof']=6
    if not "combinedataflag" in args or not args["combinedataflag"]:
        args["combinedataflag"]=1
    cmd = '{HCPPIPEDIR}/DiffusionPreprocessing/DiffPreprocPipeline_PostEddy.sh ' + \
      '--path="{path}" ' + \
      '--subject="{subject}" ' + \
      '--dwiname={dwiname} ' + \
      '--gdcoeffs={gdcoeffs} ' + \
      '--dof={dof} ' + \
      '--combine-data-flag={combinedataflag} ' + \
      '--printcom="" '
    if 'user_matrix' in args and args['user_matrix']:
        cmd = cmd + ' --user-defined-matrix="{user_matrix}" '
    cmd = cmd.format(**args)
    run(cmd, cwd=args["path"], env={"OMP_NUM_THREADS": str(args["n_cpus"])})

__version__ = open('/version').read()

parser = argparse.ArgumentParser(description='HCP Pipelines BIDS App (T1w, T2w, fMRI)')
parser.add_argument('bids_dir', help='The directory with the input dataset '
                    'formatted according to the BIDS standard.')
parser.add_argument('output_dir', help='The directory where the output files '
                    'should be stored. If you are running group level analysis '
                    'this folder should be prepopulated with the results of the'
                    'participant level analysis.')
parser.add_argument('analysis_level', help='Level of the analysis that will be performed. '
                    'Multiple participant level analyses can be run independently '
                    '(in parallel) using the same output_dir.',
                    choices=['participant'])
parser.add_argument('--participant_label', help='The label of the participant that should be analyzed. The label '
                   'corresponds to sub-<participant_label> from the BIDS spec '
                   '(so it does not include "sub-"). If this parameter is not '
                   'provided all subjects should be analyzed. Multiple '
                   'participants can be specified with a space separated list.',
                   nargs="+")
parser.add_argument('--session_label', help='The label of the session that should be analyzed. The label '
                   'corresponds to ses-<session_label> from the BIDS spec '
                   '(so it does not include "ses-"). If this parameter is not '
                   'provided, all sessions should be analyzed. Multiple '
                   'sessions can be specified with a space separated list.',
                   nargs="+")
parser.add_argument('--n_cpus', help='Number of CPUs/cores available to use.',
                   default=1, type=int)
parser.add_argument('--stages', help='Which stages to run. Space separated list.',
                   nargs="+", choices=['PreFreeSurfer', 'FreeSurfer',
                                       'PostFreeSurfer', 'fMRIVolume',
                                       'fMRISurface','DiffusionPreprocessing',
                                       'DiffusionPreprocessing_PreEddy','DiffusionPreprocessing_Eddy','DiffusionPreprocessing_PostEddy'],
                   default=['PreFreeSurfer', 'FreeSurfer', 'PostFreeSurfer',
                            'fMRIVolume', 'fMRISurface'])
parser.add_argument('--coreg', help='Coregistration method to use',
                    choices=['MSMSulc', 'FS'], default='MSMSulc')
parser.add_argument('--gdcoeffs', help='Path to gradients coefficients file',
                    default="NONE")
parser.add_argument('--license_key', help='FreeSurfer license key - letters and numbers after "*" in the email you received after registration. To register (for free) visit https://surfer.nmr.mgh.harvard.edu/registration.html',
                    required=True)
parser.add_argument('-v', '--version', action='version',
                    version='HCP Pipelines BIDS App version {}'.format(__version__))
parser.add_argument('--anat_unwarpdir', help='Unwarp direction for 3D volumes',
                    choices=['x', 'y', 'z', 'x-', 'y-', 'z-', 'NONE'], default="z")
parser.add_argument('--skip_bids_validation', '--skip-bids-validation', action='store_true',
                    default=False,
                    help='assume the input dataset is BIDS compliant and skip the validation')
parser.add_argument('--processing_mode', '--processing-mode',
                    choices=['hcp', 'legacy', 'auto'], default='hcp',
                    help='Control HCP-Pipeline mode'
                         'hcp (HCPStyleData): require T2w and fieldmap modalities'
                         'legacy (LegacyStyleData): always ignore T2w and fieldmaps'
                         'auto: use T2w and/or fieldmaps if available')
parser.add_argument('--doslicetime', help="Apply slice timing correction as part of fMRIVolume.",
                    action='store_true', default=False)
parser.add_argument('--diffusion_output_name', help="Output base name for DiffusionPreprocessing.",
                    default='Diffusion')
parser.add_argument('--diffusion_eddy_no_gpu', help="Do NOT use GPU version of eddy during DiffusionPreprocessing.",
                    action='store_true', default=False)
parser.add_argument('--diffusion_eddy_args', help="String of extra args for eddy during DiffusionPreprocessing.",
                    default='')
parser.add_argument('--diffusion_usermatrix', help="Matrix file to use instead of registering output to T1w.",
                    default='')
args = parser.parse_args()


if (args.gdcoeffs != 'NONE') and ('PreFreeSurfer' in args.stages) and (args.anat_unwarpdir == "NONE"):
    raise AssertionError('--anat_unwarpdir must be specified to use PreFreeSurfer distortion correction')

if not args.skip_bids_validation:
    run("bids-validator " + args.bids_dir)

layout = BIDSLayout(args.bids_dir, derivatives=False, absolute_paths=True)
subjects_to_analyze = []
# only for a subset of subjects
if args.participant_label:
    subjects_to_analyze = args.participant_label
# for all subjects
else:
    subject_dirs = glob(os.path.join(args.bids_dir, "sub-*"))
    subjects_to_analyze = [subject_dir.split("-")[-1] for subject_dir in subject_dirs]
# only use a subset of sessions
if args.session_label:
    session_to_analyze = dict(session=args.session_label)
else:
    session_to_analyze = dict()

# running participant level
if args.analysis_level == "participant":
    # find all T1s and skullstrip them
    for subject_label in subjects_to_analyze:
        t1ws = [f.path for f in layout.get(subject=subject_label,
                                               suffix='T1w',
                                               extensions=["nii.gz", "nii"],
                                               **session_to_analyze)]
        if len(t1ws) == 0:
            t1ws = [f.path for f in layout.get(subject=subject_label,
                                                   suffix='T1w',
                                                   extensions=["nii.gz", "nii"])]
        assert (len(t1ws) > 0), "No T1w files found for subject %s!"%subject_label

        available_resolutions = ["0.7", "0.8", "1"]
        t1_zooms = nibabel.load(t1ws[0]).header.get_zooms()
        t1_res = float(min(t1_zooms[:3]))
        t1_template_res = min(available_resolutions, key=lambda x:abs(float(x)-t1_res))
        t1_spacing = layout.get_metadata(t1ws[0])["DwellTime"]

        t2ws = [f.path for f in layout.get(subject=subject_label,
                            suffix='T2w',
                            extensions=["nii.gz", "nii"],
                            **session_to_analyze)]
        if len(t2ws) == 0:
            t2ws = [f.path for f in layout.get(subject=subject_label,
                                                   suffix='T2w',
                                                   extensions=["nii.gz", "nii"])]
        if (len(t2ws) > 0) and ( args.processing_mode != 'legacy'):
            t2_zooms = nibabel.load(t2ws[0]).header.get_zooms()
            t2_res = float(min(t2_zooms[:3]))
            t2_template_res = min(available_resolutions, key=lambda x: abs(float(x) - t2_res))
            t2_spacing = layout.get_metadata(t2ws[0])["DwellTime"]
            anat_processing_mode = "HCPStyleData"

        else:
            assert (args.processing_mode != 'hcp'), \
                f"No T2w files found for sub-{subject_label}. Consider --procesing_mode [legacy | auto ]."

            t2ws = "NONE"
            t2_template_res = "NONE"
            t2_spacing = "NONE"
            anat_processing_mode = "LegacyStyleData"

        # parse fieldmaps for structural processing
        fieldmap_set = layout.get_fieldmap(t1ws[0], return_list=True)
        fmap_args = {"fmapmag": "NONE",
                     "fmapphase": "NONE",
                     "echodiff": "NONE",
                     "t1samplespacing": "NONE",
                     "t2samplespacing": "NONE",
                     "unwarpdir": "NONE",
                     "avgrdcmethod": "NONE",
                     "SEPhaseNeg": "NONE",
                     "SEPhasePos": "NONE",
                     "echospacing": "NONE",
                     "seunwarpdir": "NONE"}

        if fieldmap_set and ( args.processing_mode != 'legacy' ):

            # use an unwarpdir specified on the command line
            # this is different from the SE direction
            unwarpdir = args.anat_unwarpdir

            fmap_args.update({"t1samplespacing": "%.8f"%t1_spacing,
                              "t2samplespacing": "%.8f"%t2_spacing,
                              "unwarpdir": unwarpdir})

            if fieldmap_set[0]["suffix"] == "phasediff":
                merged_file = "%s/tmp/%s/magfile.nii.gz"%(args.output_dir, subject_label)
                run("mkdir -p %s/tmp/%s/ && fslmerge -t %s %s %s"%(args.output_dir,
                subject_label,
                merged_file,
                fieldmap_set["magnitude1"],
                fieldmap_set["magnitude2"]))

                phasediff_metadata = layout.get_metadata(fieldmap_set["phasediff"])
                te_diff = phasediff_metadata["EchoTime2"] - phasediff_metadata["EchoTime1"]
                # HCP expects TE in miliseconds
                te_diff = te_diff*1000.0

                fmap_args.update({"fmapmag": merged_file,
                                  "fmapphase": fieldmap_set["phasediff"],
                                  "echodiff": "%.6f"%te_diff,
                                  "avgrdcmethod": "SiemensFieldMap"})
            elif fieldmap_set[0]["suffix"] == "epi":
                SEPhaseNeg = None
                SEPhasePos = None
                for fieldmap in fieldmap_set:
                    enc_dir = layout.get_metadata(fieldmap['epi'])["PhaseEncodingDirection"]
                    if "-" in enc_dir:
                        SEPhaseNeg = fieldmap['epi']
                    else:
                        SEPhasePos = fieldmap['epi']

                seunwarpdir = layout.get_metadata(fieldmap_set[0]["epi"])["PhaseEncodingDirection"]
                seunwarpdir = seunwarpdir.replace("-", "").replace("i","x").replace("j", "y").replace("k", "z")

                #TODO check consistency of echo spacing instead of assuming it's all the same
                if "EffectiveEchoSpacing" in layout.get_metadata(fieldmap_set[0]["epi"]):
                    echospacing = layout.get_metadata(fieldmap_set[0]["epi"])["EffectiveEchoSpacing"]
                elif "TotalReadoutTime" in layout.get_metadata(fieldmap_set["epi"][0]):
                    # HCP Pipelines do not allow users to specify total readout time directly
                    # Hence we need to reverse the calculations to provide echo spacing that would
                    # result in the right total read out total read out time
                    # see https://github.com/Washington-University/Pipelines/blob/master/global/scripts/TopupPreprocessingAll.sh#L202
                    print("BIDS App wrapper: Did not find EffectiveEchoSpacing, calculating it from TotalReadoutTime")
                    # TotalReadoutTime = EffectiveEchoSpacing * (len(PhaseEncodingDirection) - 1)
                    total_readout_time = layout.get_metadata(fieldmap_set[0]["epi"])["TotalReadoutTime"]
                    phase_len = nibabel.load(fieldmap_set[0]["epi"]).shape[{"x": 0, "y": 1}[seunwarpdir]]
                    echospacing = total_readout_time / float(phase_len - 1)
                else:
                    raise RuntimeError("EffectiveEchoSpacing or TotalReadoutTime not defined for the fieldmap intended for T1w image. Please fix your BIDS dataset.")

                fmap_args.update({"SEPhaseNeg": SEPhaseNeg,
                                  "SEPhasePos": SEPhasePos,
                                  "echospacing": "%.6f"%echospacing,
                                  "seunwarpdir": seunwarpdir,
                                  "avgrdcmethod": "TOPUP"})
        #TODO add support for GE fieldmaps

        struct_stages_dict = OrderedDict([("PreFreeSurfer", partial(run_pre_freesurfer,
                                                path=args.output_dir,
                                                subject="sub-%s"%subject_label,
                                                t1ws=t1ws,
                                                t2ws=t2ws,
                                                n_cpus=args.n_cpus,
                                                t1_template_res=t1_template_res,
                                                t2_template_res=t2_template_res,
                                                gdcoeffs=args.gdcoeffs,
                                                processing_mode=anat_processing_mode,
                                                **fmap_args)),
                       ("FreeSurfer", partial(run_freesurfer,
                                             path=args.output_dir,
                                             subject="sub-%s"%subject_label,
                                             n_cpus=args.n_cpus,
                                             processing_mode=anat_processing_mode)),
                       ("PostFreeSurfer", partial(run_post_freesurfer,
                                                 path=args.output_dir,
                                                 subject="sub-%s"%subject_label,
                                                 grayordinatesres=grayordinatesres,
                                                 lowresmesh=lowresmesh,
                                                 n_cpus=args.n_cpus,
                                                 regname=args.coreg,
                                                 processing_mode=anat_processing_mode))
                       ])
        for stage, stage_func in struct_stages_dict.items():
            if stage in args.stages:
                print(f'{stage} in {anat_processing_mode} mode')
                stage_func()

        bolds = [f.path for f in layout.get(subject=subject_label,
                                                suffix='bold',
                                                extensions=["nii.gz", "nii"],
                                                **session_to_analyze)]
        for fmritcs in bolds:
            fmriname = "_".join(fmritcs.split("sub-")[-1].split("_")[1:]).split(".")[0]
            assert fmriname

            fmriscout = fmritcs.replace("_bold", "_sbref")
            if not os.path.exists(fmriscout):
                fmriscout = "NONE"

            fieldmap_set = layout.get_fieldmap(fmritcs, return_list=True)
            if fieldmap_set and len(fieldmap_set) == 2 and all(item["suffix"] == "epi" for item in fieldmap_set) and ( args.processing_mode != 'legacy' ):
                SEPhaseNeg = None
                SEPhasePos = None
                for fieldmap in fieldmap_set:
                    enc_dir = layout.get_metadata(fieldmap["epi"])["PhaseEncodingDirection"]
                    if "-" in enc_dir:
                        SEPhaseNeg = fieldmap['epi']
                    else:
                        SEPhasePos = fieldmap['epi']
                echospacing = layout.get_metadata(fmritcs)["EffectiveEchoSpacing"]
                unwarpdir = layout.get_metadata(fmritcs)["PhaseEncodingDirection"]
                unwarpdir = unwarpdir.replace("i","x").replace("j", "y").replace("k", "z")
                if len(unwarpdir) == 2:
                    unwarpdir = "-" + unwarpdir[0]
                dcmethod = "TOPUP"
                biascorrection = "SEBASED"
                func_processing_mode = "HCPStyleData"
            else:
                assert (args.processing_mode != 'hcp'), \
                    f"No fieldmaps found for BOLD {fmritcs}. Consider --procesing_mode [legacy | auto ]."

                SEPhaseNeg = "NONE"
                SEPhasePos = "NONE"
                echospacing = "NONE"
                unwarpdir = "NONE"
                dcmethod = "NONE"
                biascorrection = "NONE"
                func_processing_mode = "LegacyStyleData"

            zooms = nibabel.load(fmritcs).header.get_zooms()
            fmrires = float(min(zooms[:3]))
            fmrires = "2" # https://github.com/Washington-University/Pipelines/blob/637b35f73697b77dcb1d529902fc55f431f03af7/fMRISurface/scripts/SubcorticalProcessing.sh#L43
            # While running '/usr/bin/wb_command -cifti-create-dense-timeseries /scratch/users/chrisgor/hcp_output2/sub-100307/MNINonLinear/Results/EMOTION/EMOTION_temp_subject.dtseries.nii -volume /scratch/users/chrisgor/hcp_output2/sub-100307/MNINonLinear/Results/EMOTION/EMOTION.nii.gz /scratch/users/chrisgor/hcp_output2/sub-100307/MNINonLinear/ROIs/ROIs.2.nii.gz':
            # ERROR: label volume has a different volume space than data volume

            # optional slice timing
            doslicetime = "FALSE"
            slicetimerparams = ""
            if args.doslicetime:
                doslicetime = "TRUE"
                func_processing_mode = "LegacyStyleData"
                try:
                    slicetiming = layout.get_metadata(fmritcs)["SliceTiming"]
                    tr = layout.get_metadata(fmritcs)["RepetitionTime"]
                except KeyError:
                    print(f"SliceTiming metadata is required for slice timing correction of {fmritcs}")

                try:
                    slicedirection = layout.get_metadata(fmritcs)["SliceEncodingDirection"]
                    if '-' in slicedirection:
                        slicetiming.reverse()
                except KeyError:
                    pass

                # shift timing to the median slice, assuming equally spaced slices
                slicedelta = np.diff(np.sort(slicetiming))
                slicedelta = np.mean(slicedelta[slicedelta > 0])
                slicetiming = slicetiming / (np.max(slicetiming) + slicedelta)
                slicetiming = -(slicetiming - np.median(slicetiming))

                tmpdir = f"{args.output_dir}/tmp/{subject_label}"
                Path(tmpdir).mkdir(parents=True, exist_ok=True)
                with open(f"{tmpdir}/{fmriname}_st.txt", "w") as fp:
                    fp.writelines("%f\n" % t for t in slicetiming)

                slicetimerparams = f"--repeat={tr}@--tcustom={tmpdir}/{fmriname}_st.txt"

            func_stages_dict = OrderedDict([("fMRIVolume", partial(run_generic_fMRI_volume_processsing,
                                                      path=args.output_dir,
                                                      subject="sub-%s"%subject_label,
                                                      fmriname=fmriname,
                                                      fmritcs=fmritcs,
                                                      fmriscout=fmriscout,
                                                      SEPhaseNeg=SEPhaseNeg,
                                                      SEPhasePos=SEPhasePos,
                                                      echospacing=echospacing,
                                                      unwarpdir=unwarpdir,
                                                      fmrires=fmrires,
                                                      dcmethod=dcmethod,
                                                      biascorrection=biascorrection,
                                                      n_cpus=args.n_cpus,
                                                      gdcoeffs=args.gdcoeffs,
                                                      doslicetime=doslicetime,
                                                      slicetimerparams=slicetimerparams,
                                                      processing_mode=func_processing_mode)),
                                ("fMRISurface", partial(run_generic_fMRI_surface_processsing,
                                                       path=args.output_dir,
                                                       subject="sub-%s"%subject_label,
                                                       fmriname=fmriname,
                                                       fmrires=fmrires,
                                                       n_cpus=args.n_cpus,
                                                       grayordinatesres=grayordinatesres,
                                                       lowresmesh=lowresmesh,
                                                       regname=args.coreg))
                                ])
            for stage, stage_func in func_stages_dict.items():
                if stage in args.stages:
                    print(f"Processing {fmritcs} in {func_processing_mode} mode.")
                    stage_func()

        dwis=[f.path for f in layout.get(subject=subject_label,
                                                       suffix='dwi',
                                                       extensions=["nii.gz", "nii"],**session_to_analyze)]
                                                       
        
        pos = []; neg = []
        PEdir = None; echospacing = None
        dwi_jsonfile=None
        
        for idx,dwi in enumerate(dwis):
            metadata = layout.get_metadata(dwi)
            
            #get metadata json file path so we can pass it to the eddy command
            dwi_file_entities=layout.parse_file_entities(dwi)
            dwi_file_entities['extension']='json'
            try:
                metadata_jsonfile=layout.get(**dwi_file_entities)
                if len(metadata_jsonfile)>0:
                    dwi_jsonfile=metadata_jsonfile[0].path
            except:
                pass
            
            # get phaseencodingdirection
            phaseenc = metadata['PhaseEncodingDirection']
            
            acq = 1 if 'i' in phaseenc else 2
            if not PEdir:
                PEdir = acq
            if PEdir != acq:
                raise RuntimeError("Not all dwi images have the same encoding direction (both LR and AP). Not implemented.")
            # get pos/neg
            if "-" in phaseenc:
                neg.append(dwi)
            else:
                pos.append(dwi)
            # get echospacing
            if not echospacing:
                echospacing = metadata['EffectiveEchoSpacing']*1000.
            if echospacing != metadata['EffectiveEchoSpacing']*1000.:
                raise RuntimeError("Not all dwi images have the same echo spacing. Not implemented.")

        posdata = "@".join(pos)
        negdata = "@".join(neg)

        if dwi_jsonfile:
            args.diffusion_eddy_args += f" --json={dwi_jsonfile}"
        
        diff_stages_dict = OrderedDict([("DiffusionPreprocessing", partial(run_diffusion_processsing,
                                                 path=args.output_dir,
                                                 subject="sub-%s"%subject_label,
                                                 posData=posdata,
                                                 negData=negdata,
                                                 echospacing=echospacing,
                                                 n_cpus=args.n_cpus,
                                                 PEdir=PEdir,
                                                 gdcoeffs=args.gdcoeffs,
                                                 dwiname=args.diffusion_output_name,
                                                 eddy_no_gpu=args.diffusion_eddy_no_gpu,
                                                 extra_eddy_args=args.diffusion_eddy_args))
                       ])
                       
        for stage, stage_diff in diff_stages_dict.items():
            if stage in args.stages:
                print(f"{stage} {dwis}.")
                stage_diff()
                
        diff_substages_dict = OrderedDict([("DiffusionPreprocessing_PreEddy", partial(run_diffusion_processsing_preeddy,
                                                 path=args.output_dir,
                                                 subject="sub-%s"%subject_label,
                                                 posData=posdata,
                                                 negData=negdata,
                                                 echospacing=echospacing,
                                                 n_cpus=args.n_cpus,
                                                 PEdir=PEdir,
                                                 dwiname=args.diffusion_output_name)),
                                        ("DiffusionPreprocessing_Eddy", partial(run_diffusion_processsing_eddy,
                                                 path=args.output_dir,
                                                 subject="sub-%s"%subject_label,
                                                 n_cpus=args.n_cpus,
                                                 dwiname=args.diffusion_output_name,
                                                 eddy_no_gpu=args.diffusion_eddy_no_gpu,
                                                 extra_eddy_args=args.diffusion_eddy_args)),
                                        ("DiffusionPreprocessing_PostEddy", partial(run_diffusion_processsing_posteddy,
                                                 path=args.output_dir,
                                                 subject="sub-%s"%subject_label,
                                                 n_cpus=args.n_cpus,
                                                 dwiname=args.diffusion_output_name,
                                                 gdcoeffs=args.gdcoeffs,
                                                 user_matrix=args.diffusion_usermatrix))
                       ])
        
        for stage, stage_diff in diff_substages_dict.items():
            if stage in args.stages:
                print(f"{stage} {dwis}.")
                stage_diff()
