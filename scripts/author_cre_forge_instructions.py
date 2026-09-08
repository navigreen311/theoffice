"""Author the five CRE Forge operating instructions.

    .venv/Scripts/python scripts/author_cre_forge_instructions.py

Replaces the placeholder text that four of them share - "Performs one operation against
the Forge and returns its result", byte-identical across every live cre-forge and
voiceforge instruction - and authors `assign_contract`, which had none. Clears V33 for
cre-forge and V11's missing entry.

WRITTEN FROM SOURCE, NOT FROM THE REGISTRY
==========================================

    Every section here was read out of `medlink-wholesale/backend`: the adapter's
    dispatch map and handlers in `app/api/forge.py`, and the services behind them. Where
    the adapter's own docstring had already reasoned something out - `buyer_match`'s
    `save_matches=False`, `assign_contract`'s `at_most_once` analysis - that reasoning is
    used rather than restated in different words.

    `underwrite_deal` carries a defect the manual cannot fix: every ARV it returns
    through this bridge is the seller's asking price at 0.10 confidence. That is
    docs/blocking.md B14 and medlink-wholesale#75, and the manual points at the issue so
    a reader meets the fix rather than only the caveat.

ON `compliance_coupling`
========================

    `validate_sections` rejects an empty list, and none of Greenstone's declared flags -
    `recording_consent_required`, `tsr_disclosure_required` - touches property
    underwriting. Both are voice flags. So `no_framework_applies` is used, once,
    deliberately: the same gap `NoFramework(why)` closed on the couplings side, where the
    schema has no way to state a true absence. Inventing a flag instead is exactly how
    `tsr_disclosure_required` ended up on both SimForge modules, authored generically for
    another venture and never revisited.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from broker import instructions  # noqa: E402
from broker.db import connection  # noqa: E402
from broker.humans import attributable_actor  # noqa: E402

FORGE = "cre-forge"
FORGE_API_VERSION = "1.4.0"
VERSION = "1.1.0"

NO_FRAMEWORK = ["no_framework_applies"]

SHARED_TENANT = (
    "NOT CALLER-SUPPLIED. Read from the token. It decides which properties, deals and "
    "buyers this call can reach, and an agent that thinks it can set one is wrong about "
    "the module."
)

# --------------------------------------------------------------------- property_lookup

PROPERTY_LOOKUP = {
    "what_it_does": (
        "Searches this tenant's properties by a free-text query and returns a page of "
        "them: address, city, state, zip, property type, square feet, asking price and "
        "status.\n\n"
        "A pure read. Nothing is written and nothing is sent."
    ),
    "what_it_does_not_do": (
        "IT DOES NOT VALUE ANYTHING. `asking_price` is what the record says a property "
        "is listed at. It is not an appraisal, not an after-repair value, and not "
        "evidence about what the property is worth.\n\n"
        "IT DOES NOT SEARCH THE MARKET. It searches rows this tenant already has. A "
        "property nobody has entered is absent from the answer, and that absence is a "
        "fact about the records - shared rule 1.\n\n"
        "IT DOES NOT RANK. Results come back in whatever order the query produced. "
        "Position in the list is not relevance and not quality."
    ),
    "inputs": {
        "query": (
            "REQUIRED. A non-empty string. An absent, non-string or whitespace-only "
            "value is refused 422 before the search runs."
        ),
        "page": "Optional, defaults to 1. Values below 1 are raised to 1.",
        "page_size": (
            "Optional, defaults to 25, CAPPED AT 100. The cap is applied in the adapter "
            "and is deliberate: the payload is agent-supplied, and an uncapped page size "
            "is a way to ask this Forge for the whole table. A caller asking for 500 "
            "gets 100 and no error, so ALWAYS READ page_size BACK from the response "
            "rather than assuming the request was honoured."
        ),
        "tenant": SHARED_TENANT,
    },
    "correct_sequence": [
        "Read `total` before reading `results`. `total` is the size of the whole match; "
        "`results` is one page of it. Reporting the length of the page as the number of "
        "matching properties is wrong whenever total exceeds page_size.",
    ],
    "failure_signatures": {
        "hard_failure": (
            "422 - `query` absent, not a string, or empty after stripping.\n\n"
            "401 - the tenant credential did not authenticate.\n\n"
            "THERE IS NO 404. A query matching nothing returns 200 with `total: 0` and "
            "an empty `results`. That is an answer, not a failure."
        ),
        "silent_partial": (
            "`total: 0` MEANS NO PROPERTY IN THIS TENANT'S RECORDS MATCHED THIS QUERY. "
            "It does not mean the property does not exist, is not for sale, or is not in "
            "this market. Report the query alongside the count, or the reader cannot "
            "tell an empty market from a narrow search.\n\n"
            "A SHORT `results` WITH A LARGE `total` IS PAGINATION, NOT SCARCITY. If "
            "`total` exceeds `page_size` you are holding one page. Say which.\n\n"
            "`asking_price: null` IS A MISSING RECORD, NOT A FREE PROPERTY AND NOT AN "
            "UNPRICED ONE. Never report it as zero and never omit the property from a "
            "price comparison silently - say the price is not recorded.\n\n"
            "`square_feet: null` MATTERS MORE THAN IT LOOKS. `underwrite_deal` "
            "substitutes 2000 for a missing value, so a property with no square footage "
            "here becomes a $300,000 default valuation there. See that module's manual."
        ),
    },
    "never_do": [
        "Never report the number of results on the page as the number of matching "
        "properties. Read `total`.",
        "Never report an empty result as a fact about the market. It is a fact about "
        "this tenant's records and this query string.",
        "Never treat result order as ranking, relevance or recommendation.",
        "Never report `asking_price` as a value, an appraisal or a fair price. It is a "
        "listing figure entered by a person.",
        "Never widen a search by raising `page_size` past 100 and assuming it worked. "
        "The cap is silent.",
    ],
    "retry_vs_escalate": (
        "RETRY FREELY. It is a pure read: nothing is written, nothing is sent, and a "
        "retry after a timeout costs nothing and cannot duplicate anything.\n\n"
        "ESCALATE, DO NOT RETRY, on 422. The payload is wrong and a second identical "
        "call is wrong identically.\n\n"
        "ESCALATE IF A HUMAN NEEDS PROPERTIES THIS TENANT HAS NOT RECORDED. No query "
        "reaches them. The escalation is that the data is not here, not that the search "
        "failed."
    ),
    "compliance_coupling": NO_FRAMEWORK,
}

# ----------------------------------------------------------------------- comp_analysis

COMP_ANALYSIS = {
    "what_it_does": (
        "Finds comparable sales for one property, within a radius, a recency window and "
        "a count limit, and returns them with whatever similarity data the service "
        "produced.\n\n"
        "A pure read. `SalesCompService` can persist comps through a separate "
        "`save_comps` method, and this module does not reach it - finding comparables is "
        "a question, recording them against a property is an act."
    ),
    "what_it_does_not_do": (
        "IT DOES NOT PRODUCE A VALUE. It returns comparable sales. Turning them into an "
        "after-repair value is `underwrite_deal`'s job, AND THAT MODULE DOES NOT USE "
        "THIS ONE - it computes its ARV with no comps at all. Handing these results to a "
        "human as 'the comps behind the valuation' is wrong: no valuation on this Forge "
        "is built on them. See medlink-wholesale#75.\n\n"
        "IT DOES NOT VERIFY THE SALES. The comps are records, not confirmed "
        "transactions.\n\n"
        "IT DOES NOT SAVE. Nothing about the subject property changes."
    ),
    "inputs": {
        "property_id": (
            "REQUIRED. The subject property, as a UUID. A malformed or absent value is "
            "refused 422 before anything runs."
        ),
        "radius_miles": (
            "Optional, defaults to 1.0. UNCAPPED at this boundary - unlike "
            "`property_lookup`'s page size, nothing here limits how wide an agent may "
            "search. A large radius returns comps from a different market and the "
            "response does not say so."
        ),
        "max_comps": "Optional, defaults to 10.",
        "max_age_days": (
            "Optional, defaults to 365. Widening it reaches back into older market "
            "conditions, and a sale from three years ago is returned in the same shape "
            "as one from last month."
        ),
        "tenant": SHARED_TENANT,
    },
    "correct_sequence": [
        "Choose the radius and the age window before reading the comps, and report both "
        "alongside the result. The same property returns different comparables under "
        "different parameters, and a set of comps without its parameters cannot be "
        "judged or reproduced.",
    ],
    "failure_signatures": {
        "hard_failure": (
            "422 - `property_id` absent or not a UUID.\n\n"
            "404 - no such property for this tenant.\n\n"
            "401 - the tenant credential did not authenticate."
        ),
        "silent_partial": (
            "`total: 0` IS THE COMMON CASE AND IS AN ANSWER. It means no recorded sale "
            "met the radius, age and count constraints. It does not mean the property is "
            "unusual, unsellable, or in a market without transactions - shared rule 1.\n\n"
            "A THIN SET IS NOT A WEAK MARKET. Two comps within one mile and one year is "
            "two records meeting three constraints. Report the constraints with the "
            "count.\n\n"
            "WIDENING THE PARAMETERS UNTIL COMPS APPEAR IS NOT RESEARCH. Each widening "
            "changes what the answer means, and the response carries no marker saying "
            "which parameters produced it. If you widened, say so."
        ),
    },
    "never_do": [
        "Never report comps as the basis of any valuation this Forge produced. "
        "`underwrite_deal` does not use them.",
        "Never report a comp count without the radius and age window that produced it.",
        "Never report zero comps as a fact about the property or the market.",
        "Never average the comps into a value and report it as one. That computation is "
        "not this module's and has not been reviewed as one.",
        "Never widen the radius past the subject property's own market to fill a thin "
        "result. Nothing in the response marks the comps as out-of-market.",
    ],
    "retry_vs_escalate": (
        "RETRY FREELY. A pure read, nothing written, nothing sent.\n\n"
        "ESCALATE, DO NOT RETRY, on 404: the property is not in this tenant's records "
        "and a second call will not find it.\n\n"
        "ESCALATE RATHER THAN WIDENING when a thin result is blocking a decision. "
        "Handing a human three out-of-market comps is worse than telling them there are "
        "none nearby."
    ),
    "compliance_coupling": NO_FRAMEWORK,
}

# --------------------------------------------------------------------------- buyer_match

BUYER_MATCH = {
    "what_it_does": (
        "Ranks this tenant's buyers against one deal and returns them scored, with a "
        "grade, the reasons behind the match and any potential concerns.\n\n"
        "A read. The service can persist a `BuyerMatch` row per candidate and this "
        "module passes `save_matches=False` deliberately: RANKING BUYERS IS A QUESTION; "
        "RECORDING THAT A DEAL WAS OFFERED TO THEM IS AN ACT, and an act belongs in its "
        "own module with its own grant."
    ),
    "what_it_does_not_do": (
        "IT DOES NOT OFFER THE DEAL TO ANYBODY. No buyer is contacted, no record is "
        "written, and nothing on the deal or the buyer changes. A buyer appearing at the "
        "top of this list has not been approached and does not know the deal exists.\n\n"
        "IT DOES NOT RESERVE, ALLOCATE OR PROMISE. Two callers ranking the same deal see "
        "the same buyers, and neither has any claim on them.\n\n"
        "IT DOES NOT ASSESS THE DEAL. `match_score` is about fit between a buyer and a "
        "deal. A high score on a bad deal is a well-matched bad deal."
    ),
    "inputs": {
        "deal_id": (
            "REQUIRED. The deal to match against, as a UUID. Malformed or absent is "
            "refused 422 before anything runs."
        ),
        "limit": "Optional, defaults to 50. How many ranked buyers to return.",
        "save_matches": (
            "NOT CALLER-SUPPLIED, AND FIXED AT FALSE. An agent cannot make this module "
            "write. See what_it_does."
        ),
        "tenant": SHARED_TENANT,
    },
    "correct_sequence": [
        "Read `potential_concerns` before reporting `match_score`. A high score with "
        "concerns attached is a different fact from a high score without them, and the "
        "score alone does not carry that.",
        "Read `total` before `results`. `limit` bounds the page, not the population.",
    ],
    "failure_signatures": {
        "hard_failure": (
            "422 - `deal_id` absent or not a UUID.\n\n"
            "404 - no such deal for this tenant.\n\n"
            "401 - the tenant credential did not authenticate."
        ),
        "silent_partial": (
            "`total: 0` MEANS NO BUYER IN THIS TENANT'S LIST MATCHED. It does not mean "
            "the deal is unsellable or that no buyer exists for it - it is a fact about "
            "the buyer list, which somebody built by hand. Shared rule 1.\n\n"
            "`match_score` IS RELATIVE TO THE BUYERS ON FILE. The best match in a list of "
            "three is the best of three. The number does not say how many it beat, and a "
            "grade computed over a thin list looks identical to one computed over a "
            "hundred.\n\n"
            "`match_reasons` AND `potential_concerns` ARE SERVICE-GENERATED PROSE. Pass "
            "them through as written. Summarising a concern into a clause is how it stops "
            "being read.\n\n"
            "AN EMPTY `potential_concerns` IS NOT A CLEARANCE. It means the matcher "
            "produced none, not that somebody checked and found none."
        ),
    },
    "never_do": [
        "Never report a ranked buyer as having been approached, offered the deal, or "
        "made aware of it. Nothing was sent and nothing was recorded.",
        "Never describe a match as reserved, allocated or committed. Two callers see the "
        "same list.",
        "Never report `match_score` without `potential_concerns`.",
        "Never read a high match score as a judgement about the deal. It is about fit.",
        "Never report an empty result as evidence that a deal has no buyer. It is a fact "
        "about this tenant's buyer list.",
        "Never drop or paraphrase a `potential_concerns` entry when summarising.",
    ],
    "retry_vs_escalate": (
        "RETRY FREELY. `save_matches=False` means a retry writes nothing and cannot "
        "produce a duplicate record of an offer.\n\n"
        "ESCALATE, DO NOT RETRY, on 404 - the deal is not in this tenant's records.\n\n"
        "ESCALATE RATHER THAN ACTING when a human needs a buyer contacted. This module "
        "cannot do it and no retry will. Contacting a buyer is a separate act that no "
        "module on this Forge currently performs."
    ),
    "compliance_coupling": NO_FRAMEWORK,
}

# ------------------------------------------------------------------------ underwrite_deal

UNDERWRITE_DEAL = {
    "what_it_does": (
        "Computes and STORES one analysis of a deal: an after-repair value with a "
        "low/high band and a confidence, an estimated repair cost, a maximum allowable "
        "offer, a potential profit, an ROI, and a score with a letter grade.\n\n"
        "It upserts one `DealAnalysis` row per deal. Analysing the same deal twice "
        "updates that row; it does not accumulate a history.\n\n"
        "THIS IS THE ONLY MODULE ON THIS FORGE THAT WRITES."
    ),
    "what_it_does_not_do": (
        "IT DOES NOT APPRAISE THE PROPERTY. Through this module the ARV is not derived "
        "from comparable sales, because this module never supplies any. `analyze_deal` "
        "accepts a `comps` argument and the Office adapter does not pass one, so the "
        "no-comps branch runs on every call: `arv` = the property's ASKING PRICE, "
        "`arv_low`/`arv_high` = that price +/-15%, `arv_confidence` = 0.10 - the lowest "
        "value on a scale whose maximum is 0.80.\n\n"
        "So the number this returns as an after-repair value is the seller's own asking "
        "price. It is not independent of the thing it is being used to evaluate.\n\n"
        "WHERE NO ASKING PRICE IS RECORDED it is (square_feet or 2000) x $150. A property "
        "with neither price nor square footage analyses at exactly $300,000, and nothing "
        "in the response distinguishes that constant from a computed figure except the "
        "confidence, which is 0.10 either way.\n\n"
        "THIS IS A KNOWN FORGE DEFECT WITH AN OPEN FIX, NOT A PERMANENT PROPERTY OF THE "
        "MODULE: medlink-wholesale#75 asks for a decision between the adapter supplying "
        "comps and the module refusing when it has none. Recorded on the governance side "
        "as docs/blocking.md B14. If you are reading this because a number looked wrong, "
        "the issue is where the fix is being decided - the sections below are how to work "
        "safely until it lands, not a reason to stop asking for it.\n\n"
        "IT DOES NOT DECIDE ANYTHING. It does not accept, reject, offer or contract. "
        "`max_allowable_offer` is arithmetic, not an offer."
    ),
    "inputs": {
        "deal_id": (
            "REQUIRED. The deal to analyse, as a UUID. A malformed or absent value is "
            "refused 422 before anything runs."
        ),
        "comps": (
            "NOT CALLER-SUPPLIED, AND NOT SUPPLIED AT ALL. The service accepts comparable "
            "sales; this module passes none and an agent cannot add them. This is the "
            "single most important fact about the numbers that come back - see "
            "what_it_does_not_do."
        ),
        "repair_scope": (
            "NOT CALLER-SUPPLIED. Derived from `year_built`, bucketed: >=2010 cosmetic, "
            ">=1990 moderate, >=1970 extensive, older full rehab. A property with NO "
            "`year_built` recorded is treated as 1980, which lands in extensive - an "
            "absence becomes a repair estimate."
        ),
        "tenant": SHARED_TENANT,
    },
    "correct_sequence": [
        "Read `arv_confidence` before reading `arv`. At 0.10 the ARV is the asking price "
        "restated, and every figure derived from it inherits that. Reporting the ARV "
        "first and the confidence afterwards is how the caveat gets dropped.",
        "Read the band before the midpoint. `arv_low` and `arv_high` are +/-15% of the "
        "same number, not a measured spread.",
    ],
    "failure_signatures": {
        "hard_failure": (
            "404 - no such deal, or the deal's property is missing. NotFoundError on "
            "either; the second means a deal referencing a property that is not there, "
            "which is a data fault and not an empty result.\n\n"
            "422 - `deal_id` absent or not a UUID.\n\n"
            "500 - the computation raised. NOTHING IS WRITTEN on this path; a failed "
            "analysis leaves the previous `DealAnalysis` row untouched, so a stale "
            "analysis can survive a failed re-analysis and still read as current."
        ),
        "silent_partial": (
            "THE MODULE ALWAYS SUCCEEDS. There is no empty result, no null analysis and "
            "no 'insufficient data'. Every deal with a property returns a full set of "
            "figures, and the only signal that they rest on nothing is "
            "`arv_confidence`.\n\n"
            "`arv_confidence: 0.10` IS THE NORMAL CASE HERE, NOT AN OUTLIER. It is what "
            "every call through this module returns. An agent that treats 0.10 as a rare "
            "low-confidence event has it backwards - it is the constant condition, and a "
            "call returning anything else would mean comps reached the service by some "
            "path this module does not have.\n\n"
            "ARV EQUAL TO ASKING PRICE IS NOT A COINCIDENCE. If the two match, that is "
            "the mechanism, not a market finding. Never report it as the property being "
            "priced at its after-repair value.\n\n"
            "$300,000 EXACTLY, WITH NO ASKING PRICE, IS THE DEFAULT AND NOT A VALUATION. "
            "2000 sqft x $150. Check whether `asking_price` and `square_feet` are "
            "recorded before reporting any figure from this module.\n\n"
            "`estimated_repairs` ON A PROPERTY WITH NO `year_built` IS A GUESS ABOUT A "
            "GUESS. Shared rule 1: the absence of a build year is a fact about the "
            "records, and here it silently becomes 'extensive repairs'.\n\n"
            "`max_allowable_offer` AND `potential_profit` ARE FUNCTIONS OF THE ABOVE. "
            "They carry no confidence field of their own and inherit all of it."
        ),
    },
    "never_do": [
        "Never report `arv` as a valuation, an appraisal, or what the property is worth. "
        "Through this module it is the asking price. Say which it is.",
        "Never report `arv` without `arv_confidence`. They are one fact in two fields.",
        "Never present the `arv_low`-`arv_high` band as a market range. It is the "
        "midpoint +/-15%, computed, not observed.",
        "Never report `max_allowable_offer` as an offer, a recommendation, or a price to "
        "pay. It is arithmetic over a number that came from the seller.",
        "Never treat a repeated analysis as confirmation. Two runs against unchanged "
        "inputs return identical figures by construction, and agreement between them is "
        "not evidence.",
        "Never report a figure from this module to a party outside the tenant. It is "
        "internal analysis built on unverified inputs, and it reads like a valuation.",
        "Never infer that a deal is good, bad, over- or under-priced from `deal_score` or "
        "`deal_grade` alone. The score consumes `arv_confidence`; a grade computed at "
        "0.10 confidence is a grade about the confidence as much as about the deal.",
    ],
    "retry_vs_escalate": (
        "RETRY IS SAFE AND CHANGES NOTHING. The upsert is keyed on the deal, so a retry "
        "after a timeout updates the same row rather than creating a second analysis - "
        "which is why this module is declared `natural` and not `at_most_once`. A retry "
        "cannot double-write.\n\n"
        "ESCALATE, DO NOT RETRY, on 404 for the property. A deal whose property is "
        "missing is a broken record and a second call will break identically.\n\n"
        "ESCALATE WITHOUT RETRYING if a human has asked for a valuation. This module "
        "cannot produce one, and no number of retries changes that. The escalation is: "
        "this Forge has no comparable-sales path exposed to agents - see "
        "medlink-wholesale#75."
    ),
    "compliance_coupling": NO_FRAMEWORK,
}

# ------------------------------------------------------------------------ assign_contract

ASSIGN_CONTRACT = {
    "what_it_does": (
        "Creates an assignment contract on a deal from the ASSIGNMENT template, with the "
        "signers the caller supplies, and STOPS.\n\n"
        "The contract is left at status DRAFT. It writes."
    ),
    "what_it_does_not_do": (
        "IT CREATES THE ASSIGNMENT. IT DOES NOT SEND IT. Putting the document in front of "
        "an end buyer is `send_for_signature`, a separate method on the same service, and "
        "it is not reachable from this module.\n\n"
        "That boundary is the duty, not a shortfall against it: the agent assembles the "
        "document and a human releases it. A person sending a draft they have read is "
        "circulation.\n\n"
        "IT DOES NOT VERIFY THE SIGNERS. The names and addresses come from the caller "
        "because the template does not know them - `CONTRACT_TEMPLATES[ASSIGNMENT]` "
        "declares two roles, `assignor` and `assignee`, and nothing else. Whatever is "
        "passed is what appears on the document.\n\n"
        "IT DOES NOT CHECK FOR AN EXISTING CONTRACT. There is no existence check and no "
        "unique constraint on (deal_id, contract_type). A second call creates a second "
        "draft."
    ),
    "inputs": {
        "deal_id": (
            "REQUIRED. The deal to assign, as a UUID. Malformed or absent is refused 422."
        ),
        "signers": (
            "REQUIRED. The assignor and assignee. The template supplies the roles and "
            "nothing else; these are facts about this deal, and they go onto the document "
            "as given."
        ),
        "tenant": SHARED_TENANT,
    },
    "correct_sequence": [
        "Confirm the signers with a human before calling. They are unverified caller "
        "input that goes onto a contract, and correcting them afterwards means a second "
        "draft rather than an edit.",
        "Check for an existing draft on the deal before calling. Nothing here does, and "
        "nothing underneath prevents a duplicate.",
    ],
    "failure_signatures": {
        "hard_failure": (
            "422 - `deal_id` absent or not a UUID, `signers` absent or malformed, or a "
            "field the template requires is missing.\n\n"
            "404 - no such deal for this tenant.\n\n"
            "401 - the tenant credential did not authenticate."
        ),
        "silent_partial": (
            "A 200 MEANS A DRAFT EXISTS. It does not mean anybody has seen it, agreed to "
            "it, or signed it. Never report a created contract as an executed, sent or "
            "accepted one.\n\n"
            "A TIMEOUT AFTER A SUCCESSFUL WRITE IS THE DANGEROUS CASE. The contract is "
            "created and the response is lost, so the caller cannot tell it from a call "
            "that never landed. This module is declared `at_most_once` for exactly this "
            "reason: the broker sends `Idempotency-Key` and the adapter only logs it, "
            "`create_contract_from_template` has no existence check, and `contracts` has "
            "no unique constraint to catch a duplicate underneath. NOTHING DE-DUPLICATES "
            "THIS.\n\n"
            "A DUPLICATE DRAFT IS SURVIVABLE AND MUST BE REPORTED. Somebody sees it and "
            "deletes it. That is only true while this module does not send: IF IT IS EVER "
            "EXTENDED TO SEND, the cost of a duplicate call changes from an untidy deal "
            "to a document that has left the building, and the `at_most_once` declaration "
            "above it stops covering the act."
        ),
    },
    "never_do": [
        "Never retry after a timeout. The write may have landed and nothing de-duplicates "
        "it. Report the uncertainty and let a human check the deal.",
        "Never report a created draft as sent, signed, executed or agreed.",
        "Never supply signer details an agent inferred, looked up or assumed. They go "
        "onto a contract as given.",
        "Never call this to 'check' whether a contract can be made. It writes.",
        "Never treat the absence of an error as evidence that no duplicate exists. There "
        "is no existence check to have failed.",
    ],
    "retry_vs_escalate": (
        "DO NOT RETRY. EVER. This module is `at_most_once` and means it: there is no "
        "idempotency key honoured anywhere in the path, no existence check in the service "
        "and no unique constraint in the table.\n\n"
        "ON ANY TIMEOUT OR AMBIGUOUS FAILURE, ESCALATE. Say what was attempted, on which "
        "deal, with which signers, and that it is unknown whether a draft was created. A "
        "human reading the deal can see in one look; an agent guessing produces either a "
        "duplicate or a missing contract, and both are worse than the question.\n\n"
        "ESCALATE, DO NOT RETRY, on 422 or 404."
    ),
    "compliance_coupling": NO_FRAMEWORK,
}

MANUALS = {
    "property_lookup": PROPERTY_LOOKUP,
    "comp_analysis": COMP_ANALYSIS,
    "buyer_match": BUYER_MATCH,
    "underwrite_deal": UNDERWRITE_DEAL,
    "assign_contract": ASSIGN_CONTRACT,
}


async def retire_place_call(conn) -> int:
    """Supersede `voiceforge/place_call`'s placeholder without replacing it.

    Decisions entry 20: no operating instruction is to be authored for this module. The
    exclusion row is its instruction. The eight required sections ask for the correct
    sequence, the failure signatures and the retry-vs-escalate rule of an act no agent
    may perform, and the `content_hash` of such a manual would bind a certification to
    it.

    Safe only because V11 now skips excluded modules (blocking.md B12). Before that fix
    this retirement would have made V11 demand a manual the exclusion forbids - the
    placeholder was the only thing holding that conflict off.

    It also clears V33: the shared hash `9711528544710550` survives on voiceforge alone,
    and removing one of the two leaves `transcribe_call` holding it by itself.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE forge_operating_instruction SET superseded_at = now() "
            "WHERE forge_id = 'voiceforge' AND module_id = 'place_call' "
            "AND superseded_at IS NULL"
        )
        retired = cur.rowcount
    await conn.commit()
    return retired


async def main() -> int:
    async with connection() as conn:
        actor: uuid.UUID = await attributable_actor(conn)
        for module_id, content in MANUALS.items():
            # Skip a module already live at this version rather than failing on the
            # primary key. Re-running must be safe: the retirement below is a separate
            # step, and a half-applied script that cannot be re-run leaves somebody
            # deciding which half already happened.
            existing = await instructions.live(
                conn, forge_id=FORGE, module_id=module_id
            )
            if existing is not None and existing.instruction_version == VERSION:
                print(f"  {FORGE}/{module_id} v{VERSION} already live, unchanged")
                continue
            written = await instructions.author(
                conn,
                forge_id=FORGE,
                module_id=module_id,
                instruction_version=VERSION,
                forge_api_version=FORGE_API_VERSION,
                content=content,
                authored_by=actor,
            )
            print(f"  {FORGE}/{module_id} v{VERSION} -> {written.content_hash[:16]}")

        retired = await retire_place_call(conn)
        print(f"  voiceforge/place_call placeholder retired ({retired} row) - "
              "the exclusion row is its instruction")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
