from autode.log import logger
from copy import deepcopy
from autode.transition_states.base import get_displaced_atoms_along_mode
from autode.config import Config
from autode.transition_states.templates import TStemplate
from autode.utils import requires_atoms, requires_graph
from autode.exceptions import AtomsNotFound, NoNormalModesFound
from autode.calculation import Calculation
from autode.mol_graphs import get_active_mol_graph
from autode.mol_graphs import get_truncated_active_mol_graph
from autode.methods import get_hmethod
from autode.geom import get_distance_constraints
from autode.conformers.conformer import Conformer
from autode.conformers.conf_gen import get_simanl_atoms
from autode.conformers.conformers import check_rmsd
from autode.transition_states.base import TSbase


class TransitionState(TSbase):

    @requires_graph()
    def _update_graph(self):
        """Update the molecular graph to include all the bonds that are being made/broken"""
        self.graph = get_active_mol_graph(graph=self.graph, active_bonds=self.bond_rearrangement.all)

        logger.info(f'Molecular graph updated with {len(self.bond_rearrangement.all)} active bonds')
        return None

    def _run_opt_ts_calc(self, method, name_ext):
        """Run an optts calculation and attempt to set the geometry, energy and normal modes"""

        self.optts_calc = Calculation(name=f'{self.name}_{name_ext}', molecule=self, method=method,
                                      n_cores=Config.n_cores,
                                      keywords_list=method.keywords.opt_ts,
                                      bond_ids_to_add=self.bond_rearrangement.all,
                                      other_input_block=method.keywords.optts_block)
        self.optts_calc.run()

        try:
            self.imaginary_frequencies = self.optts_calc.get_imag_freqs()
            self.set_atoms(atoms=self.optts_calc.get_final_atoms())
            self.energy = self.optts_calc.get_energy()

        except (AtomsNotFound, NoNormalModesFound):
            logger.error('Transition state optimisation calculation failed')

        return

    def _generate_conformers(self, n_confs=300):
        """Generate conformers at the TS """

        self.conformers = []

        distance_consts = get_distance_constraints(self)

        for i in range(n_confs):

            conf = Conformer(name=f'{self.name}_conf{i}', atoms=get_simanl_atoms(self, dist_consts=distance_consts, conf_n=i),
                             dist_consts=distance_consts, charge=self.charge, mult=self.mult)
            if check_rmsd(conf, self.conformers):
                conf.solvent = self.solvent
                conf.graph = deepcopy(self.graph)
                self.conformers.append(conf)

        logger.info(f'Generated {len(self.conformers)} conformer(s)')
        return None

    @requires_atoms()
    def opt_ts(self, name_ext='optts'):
        """Optimise this TS to a true TS """
        logger.info(f'Optimising {self.name} to a transition state')

        self._run_opt_ts_calc(method=get_hmethod(), name_ext=name_ext)

        # A transition state is a first order saddle point i.e. has a single imaginary frequency
        if len(self.imaginary_frequencies) == 1:
            logger.info('Found a TS with a single imaginary frequency')
            return None

        if len(self.imaginary_frequencies) == 0:
            logger.error('Transition state optimisation did not return any imaginary frequencies')
            return None

        # There is more than one imaginary frequency. Will assume that the most negative is the correct mode..
        for disp_magnitude in [1, -1]:
            self.atoms = get_displaced_atoms_along_mode(self.optts_calc, mode_number=7, disp_magnitude=disp_magnitude)
            self._run_opt_ts_calc(method=get_hmethod(), name_ext=name_ext)

            if len(self.imaginary_frequencies) == 1:
                logger.info('Displacement along second imaginary mode successful. Now have 1 imaginary mode')
                break

        return None

    def find_lowest_energy_ts_conformer(self):
        """Find the lowest energy transition state conformer by performing constrained optimisations"""
        atoms, energy, calc = deepcopy(self.atoms), deepcopy(self.energy), deepcopy(self.calc)

        self.find_lowest_energy_conformer()

        if len(self.conformers) == 1:
            logger.warning('Only found a single conformer. Not rerunning TS optimisation')
            return None

        self.opt_ts(name_ext='optts_conf')

        if self.is_true_ts() and self.energy < energy:
            logger.info('Conformer search successful')

        else:
            logger.warning(f'Transition state conformer search failed (∆E = {energy - self.energy:.4f} Ha). Reverting')
            self.set_atoms(atoms=atoms)
            self.energy = energy
            self.calc = calc

        return None

    def is_true_ts(self):
        """Is this TS a 'true' TS i.e. has at least on imaginary mode in the hessian and is the correct mode"""

        if len(self.imaginary_frequencies) > 0:
            if self.has_correct_imag_mode(bond_rearrangement=self.bond_rearrangement,  calc=self.optts_calc):
                logger.info('Found a transition state with the correct imaginary mode & links reactants and products')
                return True

        return False

    def save_ts_template(self, folder_path=Config.ts_template_folder_path):
        """Save a transition state template containing the active bond lengths, solvent_name and charge in folder_path

        Keyword Arguments:
            folder_path (str): folder to save the TS template to (default: {None})
        """
        logger.info(f'Saving TS template for {self.name}')

        truncated_graph = get_truncated_active_mol_graph(self.graph, active_bonds=self.bond_rearrangement.all)

        for bond in self.bond_rearrangement.all:
            truncated_graph.edges[bond]['distance'] = self.get_distance(*bond)

        ts_template = TStemplate(truncated_graph, solvent=self.solvent,  charge=self.charge, mult=self.mult)
        ts_template.save_object(folder_path=folder_path)

        logger.info('Saved TS template')
        return None

    def __init__(self, ts_guess, bond_rearrangement):
        """
        Transition State

        Arguments:
            ts_guess (autode.transition_states.ts_guess.TSguess)
            bond_rearrangement (autode.bond_rearrangement.BondRearrangement):
        """
        super().__init__(atoms=ts_guess.atoms, reactant=ts_guess.reactant,
                         product=ts_guess.product, name=f'TS_{ts_guess.name}')

        self.bond_rearrangement = bond_rearrangement
        self.conformers = None

        self.optts_calc = None
        self.imaginary_frequencies = []

        self._update_graph()


class SolvatedTransitionState(TransitionState):

    def __init__(self, ts_guess, bond_rearrangement, name='TS'):

        super().__init__(ts_guess=ts_guess, bond_rearrangement=bond_rearrangement, name=name)
        self.qm_solvent_xyzs = None
        self.mm_solvent_xyzs = None

        # self.charges = ts_guess.get_charges()[:self.n_atoms]
