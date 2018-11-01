from __future__ import division
import os, sys, glob, logging
import numpy as np
import pickle
import pandas as pd
import h5py
from astropy import units as u
from astropy import constants as const
from astropy.cosmology import LambdaCDM
import cfuncs as cf
import LPP_funcs as lppf
sys.path.insert(0, '/cosma5/data/dp004/dc-beck3/lib/')
import read_hdf5
import readlensing as rf
import readsnap
sys.path.insert(0, '/cosma5/data/dp004/dc-beck3/StrongLensing/LensingMap/')
#import lm_funcs_mp # Why do I need to load this???
import LM_main
from LM_main import plant_Tree # Why do I need to load this???

# Set up logging and parse arguments
logging.basicConfig(format='%(asctime)s [%(levelname)s] %(message)s',
                    level=logging.DEBUG, datefmt='%H:%M:%S')


def lensing_signal():
    # Get command line arguments
    args = {}
    args["snapnum"]      = int(sys.argv[1])
    args["simdir"]       = sys.argv[2]
    args["ladir"]        = sys.argv[3]
    args["rksdir"]        = sys.argv[4]
    args["outbase"]      = sys.argv[5]
    args["radius"]      = sys.argv[6]

    snapfile = args["simdir"]+'snapdir_%03d/snap_%03d'
    
    # Units of Simulation
    scale = rf.simulation_units(args["simdir"])

    # Cosmological Parameters
    s = read_hdf5.snapshot(45, args["simdir"])
    cosmo = LambdaCDM(H0=s.header.hubble*100,
                      Om0=s.header.omega_m,
                      Ode0=s.header.omega_l)
    h = s.header.hubble
   
    Lens = {"HF_ID" : [],
            "LC_ID" : [],
            "SrcID" : [],
            "Mdyn" : [],
            "Mlens" : [],
            "Vrms_stellar" : [],
            "Vrms_rks" : [],
            "Rein" : []}
    # Run through LensingMap output files 
    for lm_file in glob.glob(args["ladir"]+"*"+".pickle"):
        # Load LensingMap Contents
        LM = pickle.load(open(lm_file, 'rb'))
        print('Processing the following file: \n %s' % (lm_file))
        print('which contains %d lenses' % len(LM['HF_ID'][:]))
        if False not in (np.diff(LM['snapnum'][:]) <= 0):
            pass
        else:
            order = np.asarray(np.argsort(LM['snapnum'][:]))
            LM['HF_ID'] = [LM['HF_ID'][oo] for oo in order]
            LM['zl'] = [LM['zl'][oo] for oo in order]
            LM['Sources']['Src_ID'] = [LM['Sources']['Src_ID'][oo] for oo in order]
            LM['Sources']['zs'] = [LM['Sources']['zs'][oo] for oo in order]
            LM['Sources']['mu'] = [LM['Sources']['mu'][oo] for oo in order]
            LM['Sources']['Rein'] = [LM['Sources']['Rein'][oo] for oo in order]
            LM['snapnum'] = [LM['snapnum'][oo] for oo in order]
            assert False not in (np.diff(LM['snapnum'][:]) >= 0)
        
        previous_snapnum = -1
        # Run through lenses
        for ll in range(len(LM['HF_ID'])):
            # Load Lens properties
            HaloHFID = int(LM['HF_ID'][ll]) #int(LM['Rockstar_ID'][ll])
            snapnum = int(LM['snapnum'][ll])
            zl = LM['zl'][ll]

            # Only load new particle data if lens is at another snapshot
            if (previous_snapnum != snapnum):
                print('::::: Load snapshot %d' % (snapnum))
                hdata = pd.read_csv(args["rksdir"], sep='\s+', skiprows=np.arange(1, 16))
                # Load Particle Properties
                # 0 Gas, 1 DM, 4 Star[Star=+time & Wind=-time], 5 BH
                snap = snapfile % (snapnum, snapnum)
                #gas_pos = readsnap.read_block(snap, 'POS ', parttype=0)*scale
                #gas_vel = readsnap.read_block(snap, 'VEL ', parttype=0)
                star_pos = readsnap.read_block(snap, 'POS ', parttype=4)*scale
                star_age = readsnap.read_block(snap, 'AGE ', parttype=4)
                star_vel = readsnap.read_block(snap, 'VEL ', parttype=4)
                star_mass = readsnap.read_block(snap, 'MASS', parttype=4)*1e10/h
                star_pos = star_pos[star_age >= 0]
                star_vel = star_vel[star_age >= 0]
                star_mass = star_mass[star_age >= 0]
                del star_age
            previous_snapnum = snapnum

            # Load Halo Properties
            subhalo = hdata.loc[hdata['#ID'] == HaloHFID]
            if subhalo.empty:
                continue
            HPos = subhalo[['X', 'Y', 'Z']].values[0]
            Vrms = subhalo['Vrms'].values[0]*(u.km/u.s)  #[km/s]
            hvel = subhalo[['VX', 'VY', 'VZ']].values[0]
            epva = subhalo[['A[x]', 'A[y]', 'A[z]']].values[0]
            epvb = subhalo[['B[x]', 'B[y]', 'B[z]']].values[0]
            epvc = subhalo[['C[x]', 'C[y]', 'C[z]']].values[0]

            ####----> Add keys <----####
            if args["radius"] == 'Rshm':
                #Rhalfmass = hdata['Halfmass_Radius'][indx]*u.kpc
                # Stellar Half Mass Radius
                Rad_dyn = cf.call_stellar_halfmass(
                                star_pos[:, 0], star_pos[:, 1],
                                star_pos[:, 2], HPos[0],
                                HPos[1], HPos[2],
                                star_mass, Rvir.to_value('Mpc'))*u.Mpc
                if Rshm == 0.0:
                    continue
                
                ## Stellar Half Light Radius
                ### https://arxiv.org/pdf/1804.04492.pdf $3.3
            else:
                Rad_dyn = subhalo['Rvir'].values[0]*u.kpc

            ## Dynamical Mass
            star_indx = lppf.check_in_sphere(HPos, star_pos,
                                             Rad_dyn.to_value('kpc'))
            if len(star_indx[0]) > 100:
                slices = np.vstack((epva/np.linalg.norm(epva),
                                    epvb/np.linalg.norm(epvb),
                                    epvc/np.linalg.norm(epvc)))
                mdynn, vrms_s = lppf.mass_dynamical(Rad_dyn, star_vel[star_indx],
                                                  HPos, hvel, slices)
            else:
                print('!!! Not enough particles for Mdyn')
                continue
            if np.isnan(mdynn):
                print('!!! Mdyn = NaN')
                continue

            ## Lensing Mass
            # Run through sources
            for ss in range(len(LM['Sources']['Src_ID'][ll])):
                n_imgs = len(LM['Sources']['mu'][ll][ss])
                if n_imgs == 1:
                    print('!!! numer of lensing images = 1, ', n_imgs)
                    continue
                zs = LM['Sources']['zs'][ll][ss]
                Rein = LM['Sources']['Rein'][ll][ss]*u.kpc
                if Rein == 0.0:
                    print('!!! Rein = 0.0')
                    continue
                Lens['Mlens'].append(lppf.mass_lensing(Rein, zl, zs, cosmo))
                Lens['Mdyn'].append(mdynn)
                Lens["Vrms_stellar"].append(vrms_s)
                Lens["Vrms_rks"].append(Vrms)
                Lens['Rein'].append(Rein)
                Lens['HF_ID'].append(HaloHFID)
                Lens['LC_ID'].append(LM['Halo_ID'][ll])
                Lens['SrcID'].append(LM['Sources']['Src_ID'][ll][ss])
                print('Saved data of lens %d' %  (ll))
    
    df = pd.DataFrame.from_dict(Lens)
    print('Saving %d lenses to .hdf5' % (len(df.index)))
    label = args["simdir"].split('/')[-2].split('_')[-2]
    fname = (args["outbase"]+'LPP_%s.h5' % label)
    df.to_hdf(fname, key='df', mode='w')

        ## Magnitude of SNIa multiple images
        # Run through sources
        #for ss in range(len(LM['Sources']['Src_ID'][ll])):
        #    zs = LM['Sources']['zs'][ll][ss]
        #    Rein = LM['Sources']['Rein'][ll][ss]*u.kpc
        #    t = LM['Sources']['delta_t'][ll][ss]
        #    f = LM['Sources']['mu'][ll][ss]
        #    indx_max = np.argmax(t)
        #    t -= t[indx_max]
        #    t = np.absolute(t[t != 0])


if __name__ == '__main__':
    lensing_signal()
