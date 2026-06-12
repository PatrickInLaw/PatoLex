"""ocrcorrect -- the OCR text-correction ENGINE (the open-source 'correction pipeline' repo core).

Deterministic high-recall candidate generation (reunify line-break/positional-window fragment rejoin ->
over-merge split -> strict edit-1 -> corpus-aware SymSpell edit-2 candidates) + LLM context adjudication.

Run the cascade as a module from the pipeline/ root:  python -m ocrcorrect.correction_cascade
Imports within the package are absolute (from ocrcorrect.X import ...), which keeps multiprocessing-spawn
workers able to re-import by qualified name. The CA-specific dict layer (ca_gazetteer, LEGAL_SUPPLEMENT,
dict_additions) lives here for now but is intended to become injectable config for other corpora.
"""
