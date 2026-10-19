#!/bin/bash
# Reference-only public-data parser repair. Never injected into model trials.
set -e
python - <<'PATCH_REFERENCE'
from pathlib import Path
source=Path('/reference/solve.sh').read_text()
start=source.index('def get_single_fasta(pdb_id):')
end=source.index('\ndef get_pdb_title',start)
replacement = r'''def get_single_fasta(pdb_id):
    import re
    response = requests.get(
        f"https://data.rcsb.org/rest/v1/core/polymer_entity/{pdb_id.upper()}/1",
        timeout=20,
    )
    response.raise_for_status()
    entity = response.json()["entity_poly"]
    raw = entity["pdbx_seq_one_letter_code"]
    def parent_letters(match):
        code = match.group(1)
        component = requests.get(
            f"https://data.rcsb.org/rest/v1/core/chemcomp/{code}", timeout=20
        )
        component.raise_for_status()
        fields = component.json()["chem_comp"]
        letters = fields.get("one_letter_code") or ""
        if letters and all(c in "ACDEFGHIKLMNPQRSTVWY" for c in letters):
            return letters
        parents = fields.get("mon_nstd_parent_comp_id", [])
        if isinstance(parents, str):
            parents = parents.split(",")
        return "".join(THREE_TO_ONE.get(p.strip(), "X") for p in parents)
    sequence = re.sub(r"\(([^)]+)\)", parent_letters, raw)
    sequence = "".join(sequence.split())
    if "X" in sequence:
        raise ValueError(f"Unresolved modified residue in {pdb_id}")
    return sequence

'''
Path('/tmp/reference-compatible.sh').write_text(source[:start]+replacement+source[end:])
PATCH_REFERENCE
bash /tmp/reference-compatible.sh
bash /tests/test.sh
