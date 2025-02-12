"""Base classes which define the Level2 Associations"""
from collections import defaultdict
import copy
import logging
from os.path import (
    basename,
    split,
    splitext
)
import re

from jwst.associations import (
    Association,
    libpath
)
from jwst.associations.registry import RegistryMarker
from jwst.associations.lib.acid import ACID
from jwst.associations.lib.constraint import (
    Constraint,
    SimpleConstraint,
)
from jwst.associations.lib.diff import get_product_names
from jwst.associations.lib.dms_base import (
    CORON_EXP_TYPES,
    DMSAttrConstraint,
    DMSBaseMixin,
    IMAGE2_NONSCIENCE_EXP_TYPES,
    IMAGE2_SCIENCE_EXP_TYPES,
    PRODUCT_NAME_DEFAULT,
    SPEC2_SCIENCE_EXP_TYPES,
    TSO_EXP_TYPES
)
from jwst.associations.lib.member import Member
from jwst.associations.lib.rules_level3_base import _EMPTY
from jwst.associations.lib.rules_level3_base import Utility as Utility_Level3
from jwst.lib.suffix import remove_suffix

# Configure logging
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

__all__ = [
    '_EMPTY',
    'ASN_SCHEMA',
    'AsnMixin_Lv2Image',
    'AsnMixin_Lv2Special',
    'AsnMixin_Lv2Spectral',
    'Constraint_Base',
    'Constraint_Image_Nonscience',
    'Constraint_Image_Science',
    'Constraint_Mode',
    'Constraint_Single_Science',
    'Constraint_Special',
    'Constraint_Spectral_Science',
    'Constraint_Target',
    'DMSLevel2bBase',
    'DMSAttrConstraint',
    'Utility'
]

# The schema that these associations must adhere to.
ASN_SCHEMA = RegistryMarker.schema(libpath('asn_schema_jw_level2b.json'))

# Flag to exposure type
FLAG_TO_EXPTYPE = {
    'background': 'background',
}

# File templates
_DMS_POOLNAME_REGEX = 'jw(\d{5})_(\d{3})_(\d{8}[Tt]\d{6})_pool'
_LEVEL1B_REGEX = '(?P<path>.+)(?P<type>_uncal)(?P<extension>\..+)'

# Key that uniquely identfies items.
KEY = 'expname'


class DMSLevel2bBase(DMSBaseMixin, Association):
    """Basic class for DMS Level2 associations."""

    # Set the validation schema
    schema_file = ASN_SCHEMA.schema

    # Attribute values that are indicate the
    # attribute is not specified.
    INVALID_VALUES = _EMPTY

    def __init__(self, *args, **kwargs):

        super(DMSLevel2bBase, self).__init__(*args, **kwargs)

        # Initialize validity checks
        self.validity.update({
            'has_science': {
                'validated': False,
                'check': lambda member: member['exptype'] == 'science'
            },
            'allowed_candidates': {
                'validated': False,
                'check': self.validate_candidates
            }
        })

    def check_and_set_constraints(self, item):
        """Override of Association method

        An addition check is made on candidate type.
        Level 2 associations can only be created by
        OBSERVATION and BACKGROUND candidates.
        """
        match, reprocess = super(DMSLevel2bBase, self).check_and_set_constraints(item)
        if match and not self.acid.type in ['observation', 'background']:
            return False, []
        else:
            return match, reprocess

    def members_by_type(self, member_type):
        """Get list of members by their exposure type"""
        member_type = member_type.lower()
        try:
            members = self.current_product['members']
        except KeyError:
            result = []
        else:
            result = [
                member
                for member in members
                if member_type == member['exptype'].lower()
            ]

        return result

    def has_science(self):
        """Does association have a science member

        -------
        bool
            True if it does.
        """
        limit_reached = len(self.members_by_type('science')) >= 1
        return limit_reached

    def __eq__(self, other):
        """Compare equality of two assocaitions"""
        if isinstance(other, DMSLevel2bBase):
            result = self.data['asn_type'] == other.data['asn_type']
            result = result and (self.member_ids == other.member_ids)
            return result
        else:
            return NotImplemented

    def __ne__(self, other):
        """Compare inequality of two associations"""
        if isinstance(other, DMSLevel2bBase):
            return not self.__eq__(other)
        else:
            return NotImplemented

    def dms_product_name(self):
        """Define product name."""
        try:
            science = self.members_by_type('science')[0]
        except IndexError:
            return PRODUCT_NAME_DEFAULT

        try:
            science_path, ext = splitext(science['expname'])
        except Exception:
            return PRODUCT_NAME_DEFAULT

        no_suffix_path, separator = remove_suffix(science_path)
        return no_suffix_path

    def make_member(self, item):
        """Create a member from the item

        Parameters
        ----------
        item : dict
            The item to create member from.

        Returns
        -------
        member : Member
            The member
        """

        # Set exposure error status.
        try:
            exposerr = item['exposerr']
        except KeyError:
            exposerr = None

        # Create the member.
        # `is_item_tso` is used to determine whether the name should
        # represent the integrations form of the data.
        # Though coronagraphic data is not TSO,
        # it does remain in the separate integrations.
        member = Member(
            {
                'expname': Utility.rename_to_level2a(
                    item['filename'],
                    use_integrations=self.is_item_tso(item, other_exp_types=CORON_EXP_TYPES),
                ),
                'exptype': self.get_exposure_type(item),
                'exposerr': exposerr,
            },
            item=item
        )

        return member

    def _init_hook(self, item):
        """Post-check and pre-add initialization"""
        self.data['target'] = item['targetid']
        self.data['program'] = '{:0>5s}'.format(item['program'])
        self.data['asn_pool'] = basename(
            item.meta['pool_file']
        ).split('.')[0]
        self.data['constraints'] = str(self.constraints)
        self.data['asn_id'] = self.acid.id
        self.new_product(self.dms_product_name())

    def _add(self, item):
        """Add item to this association.

        Parameters
        ----------
        item : dict
            The item to be adding.
        """
        member = self.make_member(item)
        members = self.current_product['members']
        members.append(member)
        self.update_validity(member)

        # Update association state due to new member
        self.update_asn()

    def _add_items(self,
                   items,
                   meta=None,
                   product_name_func=None,
                   acid='o999',
                   **kwargs):
        """Force adding items to the association

        Parameters
        ----------
        items : [object[, ...]]
            A list of items to make members of the association.

        meta : dict
            A dict to be merged into the association meta information.
            The following are suggested to be assigned:
                - `asn_type`
                    The type of association.
                - `asn_rule`
                    The rule which created this association.
                - `asn_pool`
                    The pool from which the exposures came from
                - `program`
                    Originating observing program

        product_name_func : func
            Used if product name is 'undefined' using
            the class's procedures.

        acid : str
            The association candidate id to use. Since Level2
            associations require it, one must be specified.

        Notes
        -----
        This is a low-level shortcut into adding members, such as file names,
        to an association. All defined shortcuts and other initializations are
        by-passed, resulting in a potentially unusable association.

        `product_name_func` is used to define the product names instead of
        the default methods. The call signature is:

            product_name_func(item, idx)

        where `item` is each item being added and `idx` is the count of items.

        """
        if meta is None:
            meta = {}

        # Setup association candidate.
        if acid.startswith('o'):
            ac_type = 'observation'
        elif acid.startswith('c'):
            ac_type = 'background'
        else:
            raise ValueError(
                'Invalid association id specified: "{}"'
                '\n\tMust be of form "oXXX" or "c1XXX"'.format(acid)
            )
        self._acid = ACID((acid, ac_type))

        for idx, item in enumerate(items, start=1):
            self.new_product()
            members = self.current_product['members']
            member = Member({
                'expname': item,
                'exptype': 'science'
            }, item=item)
            members.append(member)
            self.update_validity(member)
            self.update_asn()

            # If a product name function is given, attempt
            # to use.
            if product_name_func is not None:
                try:
                    self.current_product['name'] = product_name_func(item, idx)
                except Exception:
                    logger.debug(
                        'Attempted use of product_name_func failed.'
                        ' Default product name used.'
                    )

        self.data.update(meta)
        self.sequence = next(self._sequence)

    def update_asn(self):
        """Update association info based on current members"""
        super(DMSLevel2bBase, self).update_asn()
        self.current_product['name'] = self.dms_product_name()

    def validate_candidates(self, member):
        """Allow only OBSERVATION or BACKGROUND candidates

        Parameters
        ----------
        member : Member
            Member being added. Ignored.

        Returns
        -------
        True if candidate is OBSERVATION.
        True if candidate is BACKGROUND and at least one
        member is background.
        Otherwise, False
        """

        # If an observation, then we're good.
        if self.acid.type.lower() == 'observation':
            return True

        # If a background, check that there is a background
        # exposure
        if self.acid.type.lower() == 'background':
            for member in self.current_product['members']:
                if member['exptype'].lower() == 'background':
                    return True

        # If not background member, or some other candidate type,
        # fail.
        return False

    def make_nod_asns(self):
        """Make background nod Associations

        For observing modes, such as NIRSpec MSA, exposures can be
        nodded, such that the object is in a different position in the
        slitlet. The association creation simply groups these all
        together as a single association, all exposures marked as
        `science`. When complete, this method will create separate
        associations each exposure becoming the single science
        exposure, and the other exposures then become `background`.

        Returns
        -------
        associations : [association[, ...]]
            List of new associations to be used in place of
            the current one.

        """

        for product in self['products']:
            members = product['members']

            # Split out the science vs. non-science
            # The non-science exposures will get attached
            # to every resulting association.
            science_exps = [
                member
                for member in members
                if member['exptype'] == 'science'
            ]
            nonscience_exps = [
                member
                for member in members
                if member['exptype'] != 'science'
            ]

            # Create new associations for each science, using
            # the other science as background.
            results = []
            for science_exp in science_exps:
                asn = copy.deepcopy(self)
                asn.data['products'] = None

                product_name = remove_suffix(
                    splitext(split(science_exp['expname'])[1])[0]
                )[0]
                asn.new_product(product_name)
                new_members = asn.current_product['members']
                new_members.append(science_exp)

                for other_science in science_exps:
                    if other_science['expname'] != science_exp['expname']:
                        now_background = Member(other_science)
                        now_background['exptype'] = 'background'
                        new_members.append(now_background)

                new_members += nonscience_exps

                if asn.is_valid:
                    results.append(asn)

            return results

    def __repr__(self):
        try:
            file_name, json_repr = self.ioregistry['json'].dump(self)
        except Exception:
            return str(self.__class__)
        return json_repr

    def __str__(self):
        """Create human readable version of the association
        """

        result = ['Association {:s}'.format(self.asn_name)]

        # Parameters of the association
        result.append(
            '    Parameters:'
            '        Product type: {asn_type:s}'
            '        Rule:         {asn_rule:s}'
            '        Program:      {program:s}'
            '        Target:       {target:s}'
            '        Pool:         {asn_pool:s}'.format(
                asn_type=getattr(self.data, 'asn_type', 'indetermined'),
                asn_rule=getattr(self.data, 'asn_rule', 'indetermined'),
                program=getattr(self.data, 'program', 'indetermined'),
                target=getattr(self.data, 'target', 'indetermined'),
                asn_pool=getattr(self.data, 'asn_pool', 'indetermined'),
            )
        )

        result.append('        {:s}'.format(str(self.constraints)))

        # Products of the assocation
        for product in self.data['products']:
            result.append(
                '\t{} with {} members'.format(
                    product['name'],
                    len(product['members'])
                )
            )

        # That's all folks
        result.append('\n')
        return '\n'.join(result)


@RegistryMarker.utility
class Utility():
    """Utility functions that understand DMS Level 3 associations"""

    @staticmethod
    @RegistryMarker.callback('finalize')
    def finalize(associations):
        """Check validity and duplications in an association list

        Parameters
        ----------
        associations:[association[, ...]]
            List of associations

        Returns
        -------
        finalized_associations : [association[, ...]]
            The validated list of associations
        """
        finalized_asns = []
        lv2_asns = []
        for asn in associations:
            if isinstance(asn, DMSLevel2bBase):
                finalized = asn.finalize()
                if finalized is not None:
                    lv2_asns.extend(finalized)
            else:
                finalized_asns.append(asn)
        lv2_asns = Utility.prune_duplicate_products(lv2_asns)

        # Ensure sequencing is correct.
        Utility_Level3.resequence(lv2_asns)

        return finalized_asns + lv2_asns

    @staticmethod
    def merge_asns(associations):
        """merge level2 associations

        Parameters
        ----------
        associations : [asn(, ...)]
            Associations to search for merging.

        Returns
        -------
        associatons : [association(, ...)]
            List of associations, some of which may be merged.
        """
        others = []
        lv2_asns = []
        for asn in associations:
            if isinstance(asn, DMSLevel2bBase):
                lv2_asns.append(asn)
            else:
                others.append(asn)

        lv2_asns = Utility._merge_asns(lv2_asns)

        return others + lv2_asns

    @staticmethod
    def prune_duplicate_products(asns):
        """Remove duplicate products in favor of higher level versions

        For Level 2 associations, since the products are always just the input
        exposures, different candidates can be created for each exposure. Remove
        those associations of lesser candidates.

        The assumption is that there is only one product per association, before merging

        Parameters
        ----------
        asns: [Association[,...]]
            Associations to prune

        Returns
        pruned: [Association[,...]]
            Pruned list of associations
        """
        product_names, dups = get_product_names(asns)
        if not dups:
            return asns

        pruned = copy.copy(asns)
        to_prune = defaultdict(list)
        for asn in asns:
            product_name = asn['products'][0]['name']
            if product_name in dups:
                    to_prune[product_name].append(asn)

        for product_name, asns_to_prune in to_prune.items():
            asns_to_prune = Utility.sort_by_candidate(asns_to_prune)
            for asn in asns_to_prune[1:]:
                pruned.remove(asn)

        return pruned


    @staticmethod
    def rename_to_level2a(level1b_name, use_integrations=False):
        """Rename a Level 1b Exposure to another level

        Parameters
        ----------
        level1b_name : str
            The Level 1b exposure name.

        is_integrations : boolean
            Use 'rateints' instead of 'rate' as
            the suffix.

        Returns
        -------
        str
            The Level 2a name
        """
        match = re.match(_LEVEL1B_REGEX, level1b_name)
        if match is None or match.group('type') != '_uncal':
            logger.warning((
                'Item FILENAME="{}" is not a Level 1b name. '
                'Cannot transform to Level 2a.'
            ).format(
                level1b_name
            ))
            return level1b_name

        suffix = 'rate'
        if use_integrations:
            suffix = 'rateints'
        level2a_name = ''.join([
            match.group('path'),
            '_',
            suffix,
            match.group('extension')
        ])
        return level2a_name

    @staticmethod
    def resequence(*args, **kwargs):
        return Utility_Level3.resequence(*args, **kwargs)

    @staticmethod
    def sort_by_candidate(asns):
        """Sort associations by candidate

        Parameters
        ----------
        asns: [Association[,...]]
            List of associations

        Returns
        -------
        sorted_by_candidate: [Associations[,...]]
            New list of the associations sorted.

        Notes
        -----
        The current definition of candidates allows strictly lexigraphical
        sorting:
        aXXXX > cXXXX > oXXX

        If this changes, a comparision function will need be implemented
        """
        return sorted(asns, key=lambda asn: asn['asn_id'])

    @staticmethod
    def _merge_asns(asns):
        """Merge associations by `asn_type` and `asn_id`

        Parameters
        ----------
        associations : [asn(, ...)]
            Associations to search for merging.

        Returns
        -------
        associatons : [association(, ...)]
            List of associations, some of which may be merged.
        """
        merged = {}
        for asn in asns:
            idx = '_'.join([asn['asn_type'], asn['asn_id']])
            try:
                current_asn = merged[idx]
            except KeyError:
                merged[idx] = asn
                current_asn = asn
            for product in asn['products']:
                merge_occured = False
                for current_product in current_asn['products']:
                    if product['name'] == current_product['name']:
                        member_names = set([
                            member['expname']
                            for member in product['members']
                        ])
                        current_member_names = [
                            member['expname']
                            for member in current_product['members']
                        ]
                        new_names = member_names.difference(
                            current_member_names
                        )
                        new_members = [
                            member
                            for member in product['members']
                            if member['expname'] in new_names
                        ]
                        current_product['members'].extend(new_members)
                        merge_occured = True
                if not merge_occured:
                    current_asn['products'].append(product)

        merged_asns = [
            asn
            for asn in merged.values()
        ]
        return merged_asns


# -----------------
# Basic constraints
# -----------------
class Constraint_Base(Constraint):
    """Select on program and instrument"""
    def __init__(self):
        super(Constraint_Base, self).__init__([
            DMSAttrConstraint(
                name='program',
                sources=['program']
            ),
            DMSAttrConstraint(
                name='is_tso',
                sources=['tsovisit'],
                required=False,
                force_unique=True,
            )
        ])


class Constraint_Mode(Constraint):
    """Select on instrument and optical path"""
    def __init__(self):
        super(Constraint_Mode, self).__init__([
            DMSAttrConstraint(
                name='instrument',
                sources=['instrume']
            ),
            DMSAttrConstraint(
                name='detector',
                sources=['detector']
            ),
            DMSAttrConstraint(
                name='opt_elem',
                sources=['filter', 'band']
            ),
            DMSAttrConstraint(
                name='opt_elem2',
                sources=['pupil', 'grating'],
                required=False,
            ),
            DMSAttrConstraint(
                name='opt_elem3',
                sources=['fxd_slit'],
                required=False,
            ),
            DMSAttrConstraint(
                name='subarray',
                sources=['subarray'],
                required=False,
            ),
            DMSAttrConstraint(
                name='channel',
                sources=['channel'],
                required=False,
            ),
            Constraint(
                [
                    DMSAttrConstraint(
                        sources=['detector'],
                        value='nirspec'
                    ),
                    DMSAttrConstraint(
                        sources=['filter'],
                        value='opaque'
                    ),
                ],
                reduce=Constraint.notany
            ),
            Constraint(
                [
                    DMSAttrConstraint(
                        sources=['visitype'],
                        value='.+wfsc.+',
                    ),
                ],
                reduce=Constraint.notany
            ),
            DMSAttrConstraint(
                name='slit',
                sources=['fxd_slit'],
                required=False,
            )
        ])


class Constraint_Image_Science(DMSAttrConstraint):
    """Select on science images"""
    def __init__(self):
        super(Constraint_Image_Science, self).__init__(
            name='exp_type',
            sources=['exp_type'],
            value='|'.join(IMAGE2_SCIENCE_EXP_TYPES)
        )


class Constraint_Image_Nonscience(Constraint):
    """Select on non-science images"""
    def __init__(self):
        super(Constraint_Image_Nonscience, self).__init__(
            [
                DMSAttrConstraint(
                    name='non_science',
                    sources=['exp_type'],
                    value='|'.join(IMAGE2_NONSCIENCE_EXP_TYPES),
                ),
                Constraint(
                    [
                        DMSAttrConstraint(
                            name='exp_type',
                            sources=['exp_type'],
                            value='nrs_msaspec'
                        ),
                        DMSAttrConstraint(
                            sources=['msastate'],
                            value='primarypark_allopen'
                        ),
                        DMSAttrConstraint(
                            sources=['grating'],
                            value='mirror'
                        )
                    ]
                )
            ],
            reduce=Constraint.any
        )


class Constraint_Single_Science(SimpleConstraint):
    """Allow only single science exposure

    Parameters
    ----------
    has_science_fn : func
        Function to determine whether the association
        has a science member already. No arguments are provided.

    sc_kwargs : dict
        Keyword arguments to pass to the parent class `SimpleConstraint`

    Notes
    -----
    The `has_science_fn` is further wrapped in a lambda function
    to provide a closure. Otherwise if the function is a bound method,
    that method may end up pointing to an instance that is not calling
    this constraint.
    """

    def __init__(self, has_science_fn, **sc_kwargs):
        super(Constraint_Single_Science, self).__init__(
            name='single_science',
            value=False,
            sources=lambda item: has_science_fn(),
            **sc_kwargs
        )


class Constraint_Special(DMSAttrConstraint):
    """Select on backgrounds and other auxilliary images"""
    def __init__(self):
        super(Constraint_Special, self).__init__(
            name='is_special',
            sources=[
                'bkgdtarg',
                'is_psf'
            ],
        )


class Constraint_Spectral_Science(Constraint):
    """Select on spectral science

    Parameters
    exclude_exp_types : [exp_type[, ...]]
        List of exposure types to not consider from
        from the general list.
    """

    def __init__(self, exclude_exp_types=None):
        if exclude_exp_types is None:
            general_science = SPEC2_SCIENCE_EXP_TYPES
        else:
            general_science = set(SPEC2_SCIENCE_EXP_TYPES).symmetric_difference(
                exclude_exp_types
            )

        super(Constraint_Spectral_Science, self).__init__(
            [
                DMSAttrConstraint(
                    name='exp_type',
                    sources=['exp_type'],
                    value='|'.join(general_science)
                )
            ],
            reduce=Constraint.any
        )


class Constraint_Target(DMSAttrConstraint):
    """Select on target id"""

    def __init__(self):
        super(Constraint_Target, self).__init__(
            name='target',
            sources=['targetid'],
        )


# ---------------------------------------------
# Mixins to define the broad category of rules.
# ---------------------------------------------
class AsnMixin_Lv2Image:
    """Level 2 Image association base"""

    def _init_hook(self, item):
        """Post-check and pre-add initialization"""

        super(AsnMixin_Lv2Image, self)._init_hook(item)
        self.data['asn_type'] = 'image2'


class AsnMixin_Lv2Spectral(DMSLevel2bBase):
    """Level 2 Spectral association base"""

    def _init_hook(self, item):
        """Post-check and pre-add initialization"""

        super(AsnMixin_Lv2Spectral, self)._init_hook(item)
        self.data['asn_type'] = 'spec2'


class AsnMixin_Lv2Special:
    """Process special and non-science exposures as science.
    """
    def get_exposure_type(self, item, default='science'):
        """Override to force exposure type to always be science
        Parameters
        ----------
        item : dict
            The pool entry to determine the exposure type of
        default : str or None
            The default exposure type.
            If None, routine will raise LookupError
        Returns
        -------
        exposure_type : 'science'
            Always returns as science
        """
        return 'science'
