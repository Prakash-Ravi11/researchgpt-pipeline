export const meta = {
  name: 'postfix-claim-cell-labelling',
  description: 'Blind double labelling of harvested claim->table-cell candidates against PDF page renders',
  phases: [{ title: 'Label', detail: '4 blind readers: each candidate read twice (claim-first and cell-first)' }],
}

const DIR = args.dir
const G = { G1: args.g1, G2: args.g2 }

const TARGET = { type: 'object', properties: {
  value_in_claim: { type: 'string' }, table_label: { type: 'string' }, table_page: { type: 'integer' },
  row_label_levels: { type: 'array', items: { type: 'string' } }, row_index_cell: { type: 'string' },
  column_header_levels: { type: 'array', items: { type: 'string' } }, cell_text: { type: 'string' },
  numeric_value: { type: 'number' }, other_cells_with_same_value: { type: 'integer' } },
  required: ['value_in_claim', 'table_label', 'table_page', 'row_label_levels', 'row_index_cell',
             'column_header_levels', 'cell_text', 'numeric_value', 'other_cells_with_same_value'] }
const SCHEMA = { type: 'object', properties: { labels: { type: 'array', items: { type: 'object', properties: {
  candidate_id: { type: 'string' }, claim_text_exact: { type: 'string' },
  status: { type: 'string', enum: ['VERIFIED_POSITIVE', 'WRONG_CLAIM', 'WRONG_TABLE', 'WRONG_ROW', 'WRONG_COLUMN',
                                   'WRONG_CELL', 'AMBIGUOUS', 'NOT_VERIFIABLE'] },
  claim_subject_kind: { type: 'string', enum: ['own_method', 'baseline_or_cited', 'dataset_or_cohort', 'other'] },
  table_orientation: { type: 'string', enum: ['rows_are_entities', 'columns_are_entities', 'other'] },
  targets: { type: 'array', items: TARGET }, reason: { type: 'string' }, notes: { type: 'string' } },
  required: ['candidate_id', 'claim_text_exact', 'status', 'claim_subject_kind', 'table_orientation', 'targets', 'reason', 'notes'] } } },
  required: ['labels'] }

const FILES = (ids) => `You are an independent annotator building a verified gold set of (claim sentence -> table cell) pairs from scientific PDFs. Your reading must be blind and grounded only in the PDF pages.

FILES (read-only; use ONLY these):
- ${DIR}/candidates.json -- key "candidates": harvested candidate sentences. Handle ONLY these candidate_ids: ${ids.join(', ')}.
  Fields: candidate_id, paper_id, claim_page, claim_text (the harvested sentence; table or caption text may be fused before/after the real sentence), reference ("explicit": the sentence itself names the table; "contextual": the preceding sentence, given as context_sentence, names it), table_refs (table labels), table_pages (label -> pages holding that table's caption), numbers (numbers in the sentence), numbers_on_table_pages (where those numbers also occur).
- ${DIR}/<paper_id>_p<page>.png -- page renders (claim pages and table pages). ALWAYS look at the table page image to determine table structure; also look at the claim page when the sentence is unclear.
- ${DIR}/<paper_id>_p<page>.txt -- the PDF text layer of table pages; use it only to copy characters exactly.
Do NOT open any other file (no other JSON, no repository code or outputs, no other annotator's work) and do not run any table-extraction code.`

const RULES = `STATUS -- exactly one of:
  VERIFIED_POSITIVE: a genuine natural-language claim; at least one of its values is printed in ONE determinable cell of the referenced table whose row (subject) and column (metric) agree with the claim. If the value is printed in several cells, the claim's subject/metric must single one out.
  WRONG_CLAIM: no usable claim -- not a natural-language result sentence (table content, caption, heading, equation, setup/method description), OR none of its numbers is printed in a cell of the referenced table (derived differences or ratios, counts or p-values that appear only in prose, settings mentioned in passing).
  WRONG_TABLE: the value is printed in a different table than the one referenced.
  WRONG_ROW / WRONG_COLUMN / WRONG_CELL: the value is printed in the referenced table but in a cell whose row / column / both contradict the claim.
  AMBIGUOUS: several cells fit and the claim does not decide between them, or the layout leaves the row/column unclear.
  NOT_VERIFIABLE: the table cannot be read from the render (image-only, illegible, page missing).

claim_text_exact: the single natural-language sentence inside claim_text that reports the result and (itself, or via context_sentence for "contextual" candidates) points to the table, copied CHARACTER FOR CHARACTER from claim_text -- it must be an exact contiguous substring of claim_text (keep hyphenation such as "segmen-tation" exactly as it appears). "" if there is none.

targets -- for VERIFIED_POSITIVE (and for WRONG_ROW/COLUMN/CELL, describing the cell where the value actually is), one entry per claim value that is printed in a cell:
  value_in_claim (as written in the claim, e.g. "0.923"); table_label (e.g. "Table 4", "TABLE I"); table_page (int);
  row_label_levels: the row's label(s) outer->inner exactly as printed (innermost = the label identifying this row, e.g. the method or structure name; a row under a spanning group label gives ["group", "row"]). If the row also has an index/serial-number column (01, 02, ...), do NOT use the index as the label -- put it in row_index_cell;
  row_index_cell ("" if none);
  column_header_levels: the column header(s) top->leaf exactly as printed (a multi-level header gives e.g. ["Performance Measure (Dice Score)", "Whole tumor"]);
  cell_text: the full cell content exactly as printed (e.g. "0.923 ± 0.006");
  numeric_value (number); other_cells_with_same_value (how many OTHER cells of this table print the same number).
  Claim values that are not printed in cells are not targets (mention them in notes).
  Transcription: copy characters exactly (±, %, ↑, [45]); a word broken across lines inside a narrow cell is joined as it reads ("BLEU", not "BLE U").
claim_subject_kind: own_method (the paper's own proposed method/model/result) | baseline_or_cited (another or prior method) | dataset_or_cohort (data, participants, acquisition) | other.
table_orientation: rows_are_entities (subjects/methods are rows, metrics are columns) | columns_are_entities (subjects/methods are columns) | other.
reason: 1-2 sentences on what you saw. notes: anything else ("" if nothing).
Be conservative: when unsure prefer AMBIGUOUS over a guess. Return exactly one label per assigned candidate_id.`

const CLAIM_FIRST = `PROCEDURE (claim first), for each candidate:
1. Read claim_text (and context_sentence if contextual) and find the actual claim sentence.
2. Decide what it asserts: subject (whose result), metric, value(s).
3. Open the referenced table's page render and locate the cell(s) holding each asserted value; decide the status.`

const CELL_FIRST = `PROCEDURE (cells first), for each candidate:
1. Open the referenced table's page render FIRST. For every number in the candidate's "numbers" list, find every cell of that table that prints it (note row and column of each).
2. Only then read claim_text (and context_sentence if contextual) and find the actual claim sentence and its subject and metric.
3. Decide which of the cells you found (if any) the sentence refers to; decide the status.`

phase('Label')
const jobs = [['A_claim_first', 'G1', CLAIM_FIRST], ['A_claim_first', 'G2', CLAIM_FIRST],
              ['B_cell_first', 'G1', CELL_FIRST], ['B_cell_first', 'G2', CELL_FIRST]]
const res = await parallel(jobs.map(([reader, g, proc]) => () =>
  agent(`${FILES(G[g])}\n\n${proc}\n\n${RULES}`, { label: `${reader}:${g}`, phase: 'Label', schema: SCHEMA })
    .then(r => ({ reader, group: g, labels: r ? r.labels : null }))))
const missing = res.filter(r => !r || !r.labels).length
if (missing) log(`${missing} reader run(s) returned nothing`)
return res
