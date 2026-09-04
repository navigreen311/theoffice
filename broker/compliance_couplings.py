"""Why each module implies each compliance framework, in a form that cannot be skipped.

WHAT THIS EXISTS TO PREVENT
===========================

    `forge_module_registry.compliance_flags_implied` was written in one pass for the
    nine CapitalForge modules, and **eight of the nine rows were wrong.** Four were
    empty, three under-claimed, and two named a framework the module's operating
    instruction does not cite.

    Nothing caught it. `verify_forge_modules.py --check` was green throughout: it
    checks that a registry row *resolves* against the adapter, not that its values are
    the right values, and a flag that exists is a flag that resolves. The Pack
    validator was green too — V6 and V32 compare module ids, not flags.

    The two wrong rows are the instructive ones, because they are the same error one
    step apart:

      per_connection_authorization_required on record_consent
          Matched the word "connection". It is GLBA - a BANK ACCOUNT connection.
          record_consent records consent to be contacted by email, SMS or voice.

      per_pull_authorization_required on client_read_credit
          Matched the idea of credit. It is FCRA authorisation for a bureau PULL.
          That module reads scores already on file and pulls nothing.

    Neither is a typo. Both are a plausible inference standing in for a reading, and
    both produce a row that looks considered.

THE TEST, AND WHY IT IS A SENTENCE
==================================

    For every flag on a module: **name the framework it comes from, and say why this
    module implies it.** If the sentence does not come out true, the flag is wrong.

    It has to be a sentence because the failure is semantic. A mechanical check -
    grep section 8 for `compliance/...` refs and map them through the Pack - gets
    three of the nine modules wrong, because a manual can cite an entry in order to
    scope it OUT:

      client_read     "No bureau entry applies. compliance/bureau-report-handling-v1
                      governs client_read_credit, not this module."
      record_consent  cites outbound-contact-boundary-v1 and then says recording
                      consent is not outbound contact.
      record_consent  cites application-truthfulness-v1 to explain maker-checker on
                      the SUBMIT route - a cross-reference to another module.

    A citation that scopes itself out is a disambiguation, not a coupling.

AN EMPTY LIST IS A CLAIM
========================

    Four rows were empty, and an empty list is not a neutral default: it says this
    module implies no framework at all. Nothing could tell an accidental empty from a
    considered one.

    So `NoFramework` exists and carries a reason. A module declares either couplings
    or an explicit absence, and `_validate()` refuses anything that declares neither.
    That is the stated-absence discipline the operating instructions apply to empty
    API results, applied to this table.

THIS IS DECLARATION, NOT DERIVATION
===================================

    Everything here is somebody's reading of a manual. It is not derived the way an
    adapter's `_modules` is derived, and it cannot be - a Forge does not know what a
    venture's compliance surface is, and one that told The Office which frameworks it
    implied would be asserting something about a jurisdiction it has never read.

    What this buys is that the reading is written down beside the value, so the next
    author corrects a sentence rather than guessing at a list.

THE EXPOSURE TEST
=================

    Both wrong flags were a plausible inference standing in for a reading, so the
    question worth asking before writing a module's row is: **what wrong inference is
    this module's subject matter exposed to?**

    Not a general worry. Specific, and different per module:

      client_read_credit   credit -> FCRA -> pull authorization. It reads a profile
                           somebody already pulled and pulls nothing. This inference
                           produced one of the two wrong flags.
      client_read_pii      NONE AVAILABLE. There is no pull-shaped inference from
                           "natural-person identifiers", which is why the sibling was
                           never at risk. One error, one module - not one error twice.
      record_consent       "connection" -> GLBA. Produced the other wrong flag.
      restack_recommend    restack -> placement -> advance_placement_prohibited. It
                           recommends and does not place.
      compliance_manifest  the broadest of the nine: it indexes eight record
                           collections, each with its own entry, and is named
                           "compliance". INDEXING A RECORD IS NOT IMPLYING ITS
                           FRAMEWORK.
      regulator_dossier    it leaves the building, and goes to somebody who regulates
                           Burkham. A module implies the frameworks governing what it
                           DOES, not those its recipient administers.

    Each is written into that module's `excluded` tuple below, because a flag
    correctly left off and a flag forgotten look identical in a list.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Every `runtime_flag` the Burkham Pack's `compliance_surface` declares, with the
#: framework it belongs to. Read from `packs/burkham-wickmont.draft.yaml`; a flag not
#: in this map is not a flag any Pack can propagate.
FRAMEWORKS: dict[str, str] = {
    "croa_perimeter_required": "CROA",
    "own_claims_discipline_required": "FTC_ACT",
    "client_interest_standard_required": "UDAAP",
    "advance_placement_prohibited": "UDAAP",
    "estimate_not_offer_required": (
        "STATE_COMMERCIAL_FINANCING_DISCLOSURE / MCA_DISCLOSURE_CA_SB1235"
    ),
    "per_application_authorization_required": "FALSE_STATEMENT_TO_LENDER",
    "application_truthfulness_required": "FALSE_STATEMENT_TO_LENDER",
    "card_product_discipline_required": "CARD_NETWORK_RULES",
    "facilitator_status_required": "STATE_LENDER_LICENSURE",
    "outbound_contact_boundary_required": "FTC_TSR",
    "fair_treatment_required": "ECOA",
    "recording_consent_required": "TWO_PARTY_CONSENT_RECORDING",
    "tax_advice_boundary_required": "TAX_ADVICE_SCOPE",
    "per_pull_authorization_required": "FCRA",
    "bureau_report_handling_required": "FCRA",
    "per_connection_authorization_required": "GLBA",
    "privacy_request_handling": "CCPA / STATE_PRIVACY_COMPREHENSIVE",
    "referral_fee_permitted_in_state": "REFERRAL_FEE_REGULATION",
    "trigger_term_disclosure_required": "REG_Z_ADVERTISING",
    "sb_lending_data_collection": "CFPB_1071",
}


@dataclass(frozen=True, slots=True)
class Coupling:
    """One flag on one module, with the sentence that justifies it."""

    flag: str
    #: Why THIS module implies THIS framework. Not what the framework says - what
    #: this module does that brings it into scope.
    why: str


@dataclass(frozen=True, slots=True)
class NoFramework:
    """A declared absence. An empty list with a reason attached.

    Distinct from an empty tuple of couplings, which `_validate` refuses: nothing can
    tell an accidental empty from a considered one, and four of the nine rows were
    accidental.
    """

    why: str


#: Excluded on purpose, with the sentence that excludes them. Kept beside the
#: couplings because a reader who wonders "why is bureau not on client_read?" should
#: find the answer here rather than conclude it was forgotten.
@dataclass(frozen=True, slots=True)
class Excluded:
    flag: str
    why: str


@dataclass(frozen=True, slots=True)
class ModuleCouplings:
    couplings: tuple[Coupling, ...] | NoFramework
    excluded: tuple[Excluded, ...] = ()

    @property
    def flags(self) -> list[str]:
        """What goes in `forge_module_registry.compliance_flags_implied`."""
        if isinstance(self.couplings, NoFramework):
            return []
        return [c.flag for c in self.couplings]


CAPITALFORGE: dict[str, ModuleCouplings] = {
    "client_read": ModuleCouplings(
        couplings=(
            Coupling(
                "privacy_request_handling",
                "Every record readable here is personal data subject to access and "
                "deletion requests, even though none of it is a natural-person "
                "identifier.",
            ),
            Coupling(
                "fair_treatment_required",
                "Where a read feeds a routing or recommendation decision, everything "
                "the entry says about inputs applies to what this module returns.",
            ),
        ),
        excluded=(
            Excluded(
                "bureau_report_handling_required",
                "Section 8 excludes it outright: 'No bureau entry applies. It governs "
                "client_read_credit, not this module. Nothing here is bureau-derived.'",
            ),
        ),
    ),
    "client_read_pii": ModuleCouplings(
        couplings=(
            Coupling(
                "privacy_request_handling",
                "Named the governing entry. Every record here is personal data about a "
                "named individual and reading it is a processing activity.",
            ),
            Coupling(
                "fair_treatment_required",
                "Dates of birth and addresses are exactly the inputs that entry exists "
                "to keep out of a routing decision.",
            ),
        ),
    ),
    "client_read_credit": ModuleCouplings(
        couplings=(
            Coupling(
                "bureau_report_handling_required",
                "Named the governing entry. All four endpoints return bureau-derived "
                "data, and reading it here does not widen what may be done with it.",
            ),
            Coupling(
                "fair_treatment_required",
                "This module returns exactly the inputs that entry governs, including absences.",
            ),
            Coupling(
                "privacy_request_handling",
                "Every record readable here is personal data subject to access and "
                "deletion requests.",
            ),
        ),
        excluded=(
            Excluded(
                "per_pull_authorization_required",
                "FCRA authorisation for a bureau PULL. This module reads scores "
                "already on file and pulls nothing; section 8 does not cite the entry. "
                "It was on this row until 3 September 2026, matched from the idea of "
                "credit rather than from what the module does.",
            ),
        ),
    ),
    "record_consent": ModuleCouplings(
        couplings=(
            Coupling(
                "recording_consent_required",
                "Where consent was captured on a recorded call, that recording is "
                "itself governed - explicit consent, every party, every join.",
            ),
            Coupling(
                "privacy_request_handling",
                "A consent record is personal data about a person, subject to access "
                "and deletion requests.",
            ),
        ),
        excluded=(
            Excluded(
                "per_connection_authorization_required",
                "GLBA, a BANK ACCOUNT connection. This module records consent to be "
                "contacted by email, SMS or voice. It was on this row until "
                "3 September 2026, matched on the word 'connection'.",
            ),
            Excluded(
                "outbound_contact_boundary_required",
                "Section 8 cites the entry and scopes it out: 'Recording consent is "
                "not outbound contact and does not invoke the three-part test.' A "
                "citation that scopes itself out is a disambiguation.",
            ),
            Excluded(
                "application_truthfulness_required",
                "Section 8 cites that entry to explain maker-checker on the SUBMIT "
                "route. It is a cross-reference to another module, not a claim about "
                "this one.",
            ),
        ),
    ),
    "restack_recommend": ModuleCouplings(
        couplings=(
            Coupling(
                "client_interest_standard_required",
                "The UDAAP entry. This module answers 'can this client raise more "
                "capital', and the entry is explicit that it is not the same question "
                "as 'should they'. An eligible verdict is not a recommendation.",
            ),
            Coupling(
                "bureau_report_handling_required",
                "currentUtilization is read straight from a credit profile and "
                "readinessScore embeds a credit band. Both are bureau-derived.",
            ),
            Coupling(
                "fair_treatment_required",
                "A re-stack verdict routes a client toward or away from further "
                "capital, so the disparate-impact discipline applies.",
            ),
        ),
        excluded=(
            Excluded(
                "advance_placement_prohibited",
                "The module RECOMMENDS and does not place - section 2 is explicit that "
                "an eligible verdict is an assessment, not an instruction, and "
                "placement is a separate act. The word restack invites the inference; "
                "the module does not make the placement the entry governs.",
            ),
            Excluded(
                "per_pull_authorization_required",
                "readinessScore embeds a credit band and currentUtilization is read "
                "from a credit profile, which invites exactly the inference that put "
                "this flag wrongly on client_read_credit. This module reads a profile "
                "somebody already pulled and pulls nothing.",
            ),
        ),
    ),
    "scan_communication": ModuleCouplings(
        couplings=(
            Coupling(
                "own_claims_discipline_required",
                "The FTC entry is the source of what counts as a banned claim, and "
                "this module's whole job is finding them.",
            ),
            Coupling(
                "croa_perimeter_required",
                "Credit-improvement language is a banned category here and the "
                "boundary is defined in that entry.",
            ),
            Coupling(
                "estimate_not_offer_required",
                "Where scanned text carries a lender product number, that entry "
                "governs the hedge, the provenance and the not-the-lender statement.",
            ),
            Coupling(
                "recording_consent_required",
                "Where the text is a transcript of a recorded call, that entry governs "
                "the recording it came from.",
            ),
        ),
    ),
    "submit_application": ModuleCouplings(
        couplings=(
            Coupling(
                "application_truthfulness_required",
                "The entry this module exists under. Every never in it applies at the "
                "moment of submission.",
            ),
            Coupling(
                "client_interest_standard_required",
                "A submission is a placement, and the entry is explicit that 'can this "
                "client raise capital' and 'should they' are different questions - the "
                "gates answer only the first.",
            ),
            Coupling(
                "bureau_report_handling_required",
                "Figures from a bureau report may be entered on the form; the report "
                "itself may not be attached.",
            ),
        ),
        excluded=(
            Excluded(
                "per_application_authorization_required",
                "FALSE_STATEMENT_TO_LENDER maps to two flags in the Pack and this row "
                "carried the wrong one until 3 September 2026. That framework is about "
                "the truthfulness of what is submitted, which "
                "application_truthfulness_required already carries; per-application "
                "authorization is a different claim and section 9 does not make it.",
            ),
        ),
    ),
    "compliance_manifest_assemble": ModuleCouplings(
        couplings=(
            Coupling(
                "privacy_request_handling",
                "A manifest indexes nine systems of personal data about a person, and "
                "assembling one is a read of all of them.",
            ),
            Coupling(
                "bureau_report_handling_required",
                "The documents and compliance checks include bureau-derived material; "
                "indexing it here does not widen what may be done with it.",
            ),
            Coupling(
                "application_truthfulness_required",
                "Applications and their adverse-action notices are carried, and what a "
                "manifest states about an application must match what was submitted.",
            ),
        ),
        excluded=(
            # THE BROADEST EXPOSURE OF THE NINE. This module indexes eight record
            # collections, each governed by its own entry, and it is named
            # "compliance". Both invite the same wrong inference: that assembling an
            # index of a record implies that record's framework.
            #
            # INDEXING A RECORD IS NOT IMPLYING ITS FRAMEWORK. Section 8 makes exactly
            # three claims and stops, and each is about what a manifest DOES.
            Excluded(
                "recording_consent_required",
                "Consent records are indexed. The entry governs a recording made when "
                "consent was captured; a manifest carries a reference to the record, "
                "not the recording, and indexing it neither creates nor discloses one.",
            ),
            Excluded(
                "estimate_not_offer_required",
                "Fee schedules are indexed. That entry governs how a figure is "
                "presented to a client as an estimate rather than an offer. A manifest "
                "is internal and presents nothing to a client.",
            ),
            Excluded(
                "per_connection_authorization_required",
                "ACH authorisations are indexed. GLBA governs obtaining a bank-account "
                "connection; indexing the record of one is not obtaining it.",
            ),
            Excluded(
                "client_interest_standard_required",
                "Suitability checks are indexed. The entry governs a placement "
                "decision and a manifest makes none. Its sibling "
                "regulator_dossier_export DOES carry this flag, because a dossier "
                "assembled in response to a complaint is evidence about how a client "
                "was treated - the same records, a different act.",
            ),
        ),
    ),
    "regulator_dossier_export": ModuleCouplings(
        couplings=(
            Coupling(
                "privacy_request_handling",
                "The dossier indexes personal data across systems, and it has a "
                "counterparty by design.",
            ),
            Coupling(
                "bureau_report_handling_required",
                "ACH authorisations and compliance checks carry regulated material.",
            ),
            Coupling(
                "client_interest_standard_required",
                "A dossier assembled in response to a complaint is evidence about how "
                "a client was treated, and what it omits is part of what it says.",
            ),
        ),
        excluded=(
            Excluded(
                "outbound_contact_boundary_required",
                "This artefact LEAVES THE BUILDING, which invites the inference that "
                "an outbound-contact entry applies. FTC_TSR governs telemarketing "
                "contact with a consumer. Sending an artefact to a regulator is not "
                "that, and section 8 does not make the claim.",
            ),
            Excluded(
                "own_claims_discipline_required",
                "A dossier goes to somebody who regulates Burkham, which invites the "
                "inference that every framework a regulator enforces is implied. A "
                "module implies the frameworks governing WHAT IT DOES, not those its "
                "recipient happens to administer.",
            ),
        ),
    ),
}


class CouplingError(Exception):
    """A coupling declaration is malformed. Raised at import, not at call time."""


def _validate() -> None:
    """Refuse a declaration that skips the sentence. Runs at import.

    Every failure here is one of the ways the first pass went wrong, turned into
    something that stops the process rather than something a reviewer might notice.
    """
    for module_id, decl in CAPITALFORGE.items():
        if isinstance(decl.couplings, NoFramework):
            if not decl.couplings.why.strip():
                raise CouplingError(
                    f"{module_id}: NoFramework needs a reason. An empty list is a "
                    "claim that this module implies no framework at all, and nothing "
                    "can tell an accidental empty from a considered one."
                )
        elif not decl.couplings:
            raise CouplingError(
                f"{module_id}: declares neither a coupling nor NoFramework. Use "
                "NoFramework(why=...) to say no framework applies, and say why."
            )

        seen: set[str] = set()
        for c in decl.couplings if not isinstance(decl.couplings, NoFramework) else ():
            if c.flag not in FRAMEWORKS:
                raise CouplingError(
                    f"{module_id}: {c.flag!r} is not a runtime_flag any Pack declares"
                )
            if not c.why.strip():
                raise CouplingError(
                    f"{module_id}: {c.flag!r} has no sentence. Name the framework it "
                    "comes from and say why this module implies it; if the sentence "
                    "does not come out true, the flag is wrong."
                )
            if c.flag in seen:
                raise CouplingError(f"{module_id}: {c.flag!r} declared twice")
            seen.add(c.flag)

        for e in decl.excluded:
            if e.flag not in FRAMEWORKS:
                raise CouplingError(
                    f"{module_id}: excluded flag {e.flag!r} is not a declared runtime_flag"
                )
            if not e.why.strip():
                raise CouplingError(
                    f"{module_id}: exclusion of {e.flag!r} has no reason. A flag left "
                    "off without a stated reason reads as forgotten."
                )
            if e.flag in seen:
                raise CouplingError(f"{module_id}: {e.flag!r} is both coupled and excluded")


_validate()


def flags_for(forge_id: str, module_id: str) -> list[str]:
    """What `forge_module_registry.compliance_flags_implied` should hold.

    Raises rather than defaulting to empty. A module with no declaration is not a
    module with no frameworks - it is a module nobody has read yet, and returning
    `[]` would write that reading into the database as though somebody had.
    """
    if forge_id.lower() != "capitalforge":
        raise CouplingError(
            f"no coupling declarations for {forge_id!r}. Read its manuals' section 8 "
            "and write them down before registering rows."
        )
    decl = CAPITALFORGE.get(module_id)
    if decl is None:
        raise CouplingError(
            f"{module_id!r} has no coupling declaration. Name the frameworks its "
            "operating instruction cites, or declare NoFramework with a reason - "
            "an empty list written by default is a claim nobody made."
        )
    return decl.flags
