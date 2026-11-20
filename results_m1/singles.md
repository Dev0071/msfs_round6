# M1: single faults per configuration (descriptive)

Detected = the injected class named and nothing else. For F_D: no component named. Lower = one-sided 97.5% CP lower bound.

| class | n | sigma_r8 | sigma_hash_plus | span_otel_default | span_otel_content | span_openinference | span_openinference_guard |
|---|---|---|---|---|---|---|---|
| F_R | 96 | 96 (0.96) | 96 (0.96) | 0 (0.00) | 96 (0.96) | 96 (0.96) | 96 (0.96) |
| F_X | 96 | 96 (0.96) | 96 (0.96) | 0 (0.00) | 0 (0.00) | 96 (0.96) | 96 (0.96) |
| F_T | 96 | 96 (0.96) | 96 (0.96) | 0 (0.00) | 0 (0.00) | 0 (0.00) | 0 (0.00) |
| F_P | 96 | 96 (0.96) | 96 (0.96) | 0 (0.00) | 0 (0.00) | 0 (0.00) | 58 (0.50) |
| F_D | 96 | 96 (0.96) | 96 (0.96) | 96 (0.96) | 96 (0.96) | 96 (0.96) | 96 (0.96) |
| clean, no alarm | 240 | 240 | 240 | 240 | 240 | 240 | 240 |

## Harmed single faults only

| class | n harmed | sigma_r8 | sigma_hash_plus | span_otel_default | span_otel_content | span_openinference | span_openinference_guard |
|---|---|---|---|---|---|---|---|
| F_R | 17 | 17 | 17 | 0 | 17 | 17 | 17 |
| F_X | 10 | 10 | 10 | 0 | 0 | 10 | 10 |
| F_T | 7 | 7 | 7 | 0 | 0 | 0 | 0 |
| F_P | 58 | 58 | 58 | 0 | 0 | 0 | 58 |

## What else was named (single runs where the injected class was not the only alarm)

- span_otel_content: F_X → ['F_R'] ×96
