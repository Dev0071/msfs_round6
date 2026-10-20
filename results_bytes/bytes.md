# Record sizes, measured (hotpotqa, backend llama3.1:8b, 360 runs)

| record | estimate | median (bin) | p95 (bin) | max (bin) | median (json) |
|---|---:|---:|---:|---:|---:|
| sigma0 | 532 | 69 | 90 | 203 | 103 |
| otel_default | 136 | 166 | 170 | 170 | 200 |
| otel_content | 3,940 | 3,434 | 5,357 | 8,991 | 3,444 |
| openinference | 8,740 | 5,261 | 8,805 | 14,546 | 5,281 |
| openinference_guard | 8,836 | 5,386 | 8,930 | 14,671 | 5,440 |
| sigma_star | 3,688 | 3,383 | 5,374 | 8,988 | 3,587 |
| sigma_star_plus | 3,720 | 3,413 | 5,390 | 9,032 | 3,625 |
| sigma_hash | 1,085 | 800 | 1,479 | 2,523 | 1,106 |
| sigma_hash_plus | 1,117 | 847 | 1,526 | 2,570 | 1,187 |
| sigma_max | 30,433 | 5,756 | 9,286 | 15,055 | 6,090 |

| input | median chars | p95 | max |
|---|---:|---:|---:|
| question_chars | 94 | 169 | 241 |
| passage_chars | 1,867 | 3,792 | 5,392 |
| output_chars | 19 | 40 | 153 |
| prompt_chars | 2,665 | 4,457 | 7,191 |
