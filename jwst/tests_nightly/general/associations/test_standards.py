"""Test against Level2 standard associations
"""
from pathlib import Path
import pytest

from jwst.associations.lib.diff import (
    compare_asn_files,
)
from jwst.associations.tests.helpers import (
    combine_pools,
    t_path
)
from jwst.tests.base_classes import BaseJWSTTest

from jwst.associations.main import Main

# #################
# Setup environment
# #################

# Main test args
TEST_ARGS = ['--no-merge']

# Produce Level2b only associations
LV2_ONLY_ARGS = [
    '-r',
    t_path('../lib/rules_level2b.py'),
    '--ignore-default',
    '--no-merge'
]

# Produce Level3 only associations
LV3_ONLY_ARGS = [
    '-r',
    t_path('../lib/rules_level3.py'),
    '--ignore-default',
    '--no-merge'
]

# Produce general associations
DEF_ARGS = []


# Define the standards
class MakePars():
    def __init__(
            self,
            pool_root,
            main_args=DEF_ARGS,
            source=None,
            outdir=None,
            execute=True,
            xfail=None
    ):
        self.pool_root = pool_root
        self.main_args = main_args
        self.source = source
        self.outdir = outdir
        self.execute = execute
        self.xfail = xfail


standards = [
    MakePars('pool_002_image_miri', main_args=LV3_ONLY_ARGS),
    MakePars('pool_004_wfs'),
    MakePars('pool_005_spec_niriss'),
    MakePars('pool_006_spec_nirspec'),
    MakePars('pool_007_spec_miri'),
    MakePars('pool_009_spec_miri_lv2bkg'),
    MakePars('pool_010_spec_nirspec_lv2bkg'),
    MakePars('pool_011_spec_miri_lv2bkg_lrs'),
    MakePars('pool_013_coron_nircam'),
    MakePars('pool_014_ami_niriss'),
    MakePars('pool_015_spec_nirspec_lv2bkg_reversed', main_args=LV2_ONLY_ARGS),
    MakePars('pool_016_spec_nirspec_lv2bkg_double', main_args=LV2_ONLY_ARGS),
    MakePars('pool_017_spec_nirspec_lv2imprint'),
    MakePars('pool_018_all_exptypes', main_args=LV2_ONLY_ARGS),
    MakePars('pool_019_niriss_wfss'),
    MakePars('pool_020_00009_image_miri'),
    MakePars('pool_021_tso'),
    MakePars('pool_022_tso_noflag'),
    MakePars('pool_023_nirspec_msa_3nod', main_args=LV2_ONLY_ARGS),
    MakePars('pool_024_nirspec_fss_nods'),
    MakePars('pool_025_nirspec_fss_nod_chop'),
    MakePars('pool_026_mir_image_tso'),
    MakePars('pool_027_nirspec_ifu_nods'),
    MakePars('pool_028_mir_lrsfs_nods'),
]


# #####
# Tests
# #####
class TestAgainstStandards(BaseJWSTTest):
    input_loc = 'associations'
    test_dir = 'standards'
    ref_loc = [test_dir, 'truth']

    @pytest.mark.parametrize(
        'standard_pars',
        standards
    )
    def test_against_standard(self, standard_pars):
        """Compare a generated assocaition against a standard

        Success is when no other AssertionError occurs.
        """
        if standard_pars.xfail is not None:
            pytest.xfail(reason=standard_pars.xfail)

        # Create the associations
        generated_path = Path('generate')
        generated_path.mkdir()
        version_id = standard_pars.pool_root.replace('_', '-')
        args = TEST_ARGS + standard_pars.main_args + [
            '-p', str(generated_path),
            '--version-id', version_id,
        ]
        pool = combine_pools([
            t_path(Path('data') / (standard_pars.pool_root + '.csv'))
        ])
        Main(args, pool=pool )

        # Retrieve the truth files
        truth_paths = [
            self.get_data(truth_path)
            for truth_path in self.data_glob(*self.ref_loc, glob='*_' + version_id + '_*.json')
        ]

        # Compare the association sets.
        try:
            compare_asn_files(generated_path.glob('*.json'), truth_paths)
        except AssertionError:
            if standard_pars.xfail:
                pytest.xfail(standard_pars.xfail)
            else:
                raise

    def test_specified_standard_pool(self, standard_pool):
        """Test against a standard pool specified from the command-line"""
        if standard_pool:
            for standard_pars in standards:
                if standard_pars.pool_root == standard_pool:
                    break
            else:
                assert False, f'Pool "{standard_pool}" specified by `--standard_pool` is not in test set.'

            # Add debugging since this is doing only a specific file.
            standard_pars.main_args.append('-D')
            self.test_against_standard(standard_pars)
        else:
            pytest.skip('No standard pool specified using `--standard_pool` command-line option.')
