from pathlib import Path
import importlib
from pkgutil import iter_modules

import pytest

from .base_classes import (
    BaseJWSTTest,
    _data_glob_local,
    _data_glob_url
)
from .helpers import word_precision_check

def test_word_precision_check():
    """Test word_precision_check"""
    s1 = "a b c"
    s2 = "aa bb cc"
    s3 = "aa bb cc dd"
    s4 = "aazz bbzz cczz"

    assert word_precision_check(s1, s1)
    assert not word_precision_check(s1, s2)
    assert word_precision_check(s1, s2, length=1)
    assert not word_precision_check(s2, s3)
    assert word_precision_check(s2, s4, length=2)


@pytest.mark.usefixtures('_jail')
@pytest.mark.parametrize(
    'glob_filter, nfiles',
    [
        ('*', 3),
        ('*.txt', 3),
        ('*.fits', 0)
    ]
)
def test_data_glob_local(glob_filter, nfiles):
    """Test working of local globbing

    Parameters
    ----------
    glob_filter: str
        The glob filter to use.

    nfiles: int
        The number of files expected to find.
    """
    path = Path('datadir')
    path.mkdir()
    for idx in range(3):
        with open(path / ('afile' + str(idx) + '.txt'), 'w') as fh:
            fh.write(f'I am file {idx}')

    files = _data_glob_local(path, glob_filter)
    assert len(files) == nfiles


@pytest.mark.bigdata
@pytest.mark.parametrize(
    'glob_filter, nfiles',
    [
        ('*', 1),
        ('*.txt', 0),
        ('*.fits', 1)
    ]
)
def test_data_glob_url(glob_filter, nfiles):
    """Test globbing over a URL

    Parameters
    ----------
    glob_filter: str
        The glob filter to use.

    nfiles: int
        The number of files expected to find.
    """
    root = 'https://bytesalad.stsci.edu/artifactory/'
    path = 'jwst-pipeline/dev/nircam/test_bias_drift'

    files = _data_glob_url(path, glob_filter, root=root)
    assert len(files) == nfiles


class TestBaseJWSTTest(BaseJWSTTest):
    """Test globbing from the class"""

    input_loc = 'nircam'
    ref_loc = ['test_bias_drift', 'truth']

    @pytest.mark.parametrize(
        'glob_filter, nfiles',
        [
            ('*', [1, 2]),
            ('*.txt', [0]),
            ('*.fits', [1])
        ]
    )
    def test_glob(self, glob_filter, nfiles):
        """Test data globbing

        Ensure glob gets the right files.

        Parameters
        ----------
        glob_filter: str
            The `glob`-like filter to use.

        nfiles: [int[,...]]
            Number of files expected to be returned.
            List because the number can change depending on whether
            url-based artifactory location or local.
        """
        files = self.data_glob('test_bias_drift', glob=glob_filter)
        assert len(files) in nfiles


def test_submodules_can_be_imported():
    """Make sure all package submodules can be imported"""
    import jwst

    submodules = [mod for _, mod, ispkg in iter_modules(jwst.__path__) if ispkg]
    # Ignore timeconversion which has non-standard env vars and dependencies
    submodules.remove('timeconversion')
    for module in submodules:
        importlib.import_module("jwst." + module)
