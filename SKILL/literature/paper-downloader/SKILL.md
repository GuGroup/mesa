---
description: Use this skill whenever the user wants to download academic papers or research PDFs using DOI, arXiv ID, title, or URL. Triggers include "논문 다운로드", "download paper", "get PDF", "sci-hub", "fetch article".
---

# Paper Downloader
This skill provides reliable academic paper PDF download functionality based on the provided Sci-Hub resolver script.

## Core Script
The file `scripts/scihub_resolver.py` contains the complete original Sci-Hub resolver code you supplied.

## Installation

```bash

pip install curl-cffi

```



## Basic Usage



```python

from scripts.scihub_resolver import SciHubResolver



# Create resolver

resolver = SciHubResolver()



# Resolve DOI to PDF link

links = resolver.resolve("10.1038/nature12345")



if links:

    # Download PDF bytes

    pdf_bytes, content_type, final_url = resolver.client.fetch(links[0].url)

    

    # Save file

    with open("paper.pdf", "wb") as f:

        f.write(pdf_bytes)

    

    print("Download completed:", final_url)

```



## Batch Download



```python

dois = ["doi1", "doi2", "doi3"]



for doi in dois:

    links = resolver.resolve(doi)

    if links:

        content, _, _ = resolver.client.fetch(links[0].url)

        filename = doi.replace("/", "_").replace(".", "_") + ".pdf"

        with open(filename, "wb") as f:

            f.write(content)

```



## Features



- Automatic mirror discovery and rotation

- curl_cffi Chrome impersonation for Cloudflare/DDoS-Guard bypass

- GET → POST fallback

- Graceful fallback when curl_cffi is not available



## Commands



```bash

# Test download

python -c '

from scripts.scihub_resolver import SciHubResolver

r = SciHubResolver()

links = r.resolve("YOUR_DOI")

print(links)

'

```
