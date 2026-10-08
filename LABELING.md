# Labelling guide for label_sheet.csv

For each row, read the question, the gold answer and the model's output, and
put one of these in the `label` column:

| label | when |
|---|---|
| `1` | A reader would take the output as giving the gold answer. Equivalent forms count: "JFK" for "John F. Kennedy", "1,000" for "1000", a correct answer inside a full sentence. |
| `0` | It gives a different answer, refuses or says the material does not say, or hedges between candidates without committing to the gold one ("it could be X or Y"). |
| `?` | You genuinely cannot tell, for example when the gold answer itself looks wrong or the question is ambiguous. Use it sparingly; these rows are excluded. |

Rules:

- Judge only whether the output answers with the gold answer. Do not judge
  style, length or politeness.
- An output that mentions the gold answer but asserts something else is `0`.
  The sheet includes cases like this on purpose.
- Do not look anything up, and do not check the scorer results first. The
  sheet is blind on purpose.
- Use `notes` for anything odd. Notes are not scored.

A second annotator works on a separate copy of the sheet. Do not discuss
items before both copies are done.
