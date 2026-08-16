# 14 --- Evaluation Strategy

## 1. Goal

Measure whether the Harness is actually useful, not merely whether it
runs.

## 2. Golden dataset

Create a fixture set containing: - 20 text-heavy pages; - 20 image-heavy
pages; - 20 mixed pages; - 10 duplicate groups; - 10 historical-version
cases; - 20 representative questions.

Each question has expected evidence IDs.

## 3. Retrieval metrics

-   Recall@5
-   Recall@10
-   MRR
-   nDCG

## 4. Answer metrics

-   citation precision
-   citation recall
-   unsupported claim rate
-   answer correctness
-   evidence coverage

## 5. Multimodal metrics

-   diagram component precision
-   relationship precision
-   OCR accuracy where ground truth exists
-   visual classification accuracy

## 6. Cost metrics

-   tokens per artifact
-   cost per artifact
-   cost per successful answer
-   percentage of images escalated
-   duplicate savings

## 7. Acceptance targets for MVP

Initial targets are configurable; suggested: - retrieval Recall@10 \>=
0.85 on golden set; - citation validity \>= 0.98; - unsupported claim
rate \<= 0.02; - exact duplicates indexed once as canonical evidence; -
unchanged artifacts cause zero LLM enrichment calls; - repeated image
checksums cause zero duplicate deep-vision calls.

Do not treat these as universal production guarantees. They are initial
engineering gates.
