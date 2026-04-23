# Graph Report - worked/express-deck  (2026-04-24)

## Corpus Check
- Large corpus: 31 files · ~605,500 words. Semantic extraction will be expensive (many Claude tokens). Consider running on a subfolder, or use --no-semantic to run AST-only.

## Summary
- 18 nodes · 22 edges · 3 communities detected
- Extraction: 68% EXTRACTED · 32% INFERRED · 0% AMBIGUOUS · INFERRED: 7 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]

## God Nodes (most connected - your core abstractions)
1. `generator()` - 5 edges
2. `generate_template()` - 4 edges
3. `url_to_image()` - 3 edges
4. `image_to_base64()` - 3 edges
5. `generate_content()` - 3 edges
6. `get_content_from_openai()` - 2 edges
7. `render_pdfkit()` - 2 edges
8. `get_unsplash_img()` - 2 edges
9. `get_pexels_img()` - 2 edges
10. `generate_sd_image()` - 2 edges

## Surprising Connections (you probably didn't know these)
- `generator()` --calls--> `render_pdfkit()`  [INFERRED]
  /mnt/windows-ssd/Projects/memory/graphify/worked/express-deck/api.py → /mnt/windows-ssd/Projects/memory/graphify/worked/express-deck/functions/content_functions.py
- `generate_content()` --calls--> `get_content_from_openai()`  [INFERRED]
  /mnt/windows-ssd/Projects/memory/graphify/worked/express-deck/functions/main_functions.py → /mnt/windows-ssd/Projects/memory/graphify/worked/express-deck/functions/content_functions.py
- `generate_template()` --calls--> `generate_sd_image()`  [INFERRED]
  /mnt/windows-ssd/Projects/memory/graphify/worked/express-deck/functions/main_functions.py → /mnt/windows-ssd/Projects/memory/graphify/worked/express-deck/functions/images_functions.py
- `generator()` --calls--> `image_to_base64()`  [INFERRED]
  /mnt/windows-ssd/Projects/memory/graphify/worked/express-deck/api.py → /mnt/windows-ssd/Projects/memory/graphify/worked/express-deck/functions/images_functions.py
- `generator()` --calls--> `generate_content()`  [INFERRED]
  /mnt/windows-ssd/Projects/memory/graphify/worked/express-deck/api.py → /mnt/windows-ssd/Projects/memory/graphify/worked/express-deck/functions/main_functions.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.38
Nodes (4): generate_sd_image(), get_pexels_img(), get_unsplash_img(), url_to_image()

### Community 1 - "Community 1"
Cohesion: 0.6
Nodes (4): generator(), image_to_base64(), generate_content(), generate_template()

### Community 2 - "Community 2"
Cohesion: 0.67
Nodes (2): get_content_from_openai(), render_pdfkit()

## Knowledge Gaps
- **Thin community `Community 2`** (3 nodes): `get_content_from_openai()`, `render_pdfkit()`, `content_functions.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `generator()` connect `Community 1` to `Community 2`, `Community 3`?**
  _High betweenness centrality (0.471) - this node is a cross-community bridge._
- **Why does `image_to_base64()` connect `Community 1` to `Community 0`?**
  _High betweenness centrality (0.353) - this node is a cross-community bridge._
- **Why does `generate_template()` connect `Community 1` to `Community 0`?**
  _High betweenness centrality (0.129) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `generator()` (e.g. with `image_to_base64()` and `generate_content()`) actually correct?**
  _`generator()` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `generate_template()` (e.g. with `generator()` and `image_to_base64()`) actually correct?**
  _`generate_template()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `image_to_base64()` (e.g. with `generator()` and `generate_template()`) actually correct?**
  _`image_to_base64()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `generate_content()` (e.g. with `generator()` and `get_content_from_openai()`) actually correct?**
  _`generate_content()` has 2 INFERRED edges - model-reasoned connections that need verification._