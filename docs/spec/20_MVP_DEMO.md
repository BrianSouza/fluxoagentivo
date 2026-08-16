# 20 --- MVP Demonstration Scenario

The first end-to-end demonstration should simulate the user's actual
problem.

## Dataset

Create a synthetic Confluence-like page containing:

1.  text explaining a mobile application;
2.  an application flow diagram;
3.  a screenshot showing a WebView;
4.  a backend architecture diagram;
5.  repetitive boilerplate text;
6.  a duplicate page.

## Question

"Explain how the mobile application checkout flow works today, including
the WebView and backend services."

## Expected behavior

The system: 1. ingests the page; 2. extracts text; 3. identifies images;
4. detects boilerplate; 5. detects duplicate page; 6. interprets the two
diagrams; 7. connects visual evidence to page context; 8. creates a
KnowledgeUnit; 9. indexes text and visual descriptions; 10. retrieves
relevant evidence; 11. answers the question; 12. cites: - source page; -
relevant section; - diagram/image; - backend evidence.

## Cost test

Run ingestion twice.

First run: - AI enrichment occurs for relevant images.

Second run: - unchanged artifacts produce zero deep multimodal calls.

Then modify only one image.

Expected: - only that image and affected KnowledgeUnits are reprocessed.

## Provider portability test

Run the same test with: - configured cloud provider; - configured Ollama
model.

Application code must not change.
