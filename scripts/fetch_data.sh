#!/usr/bin/env bash
# Download the public files used for the README numbers into a data folder (default ./data).
# Nothing from these files is committed to the repository.
set -euo pipefail
dir="${1:-data}"
mkdir -p "$dir"
cd "$dir"
hf=https://huggingface.co/datasets
curl -sSLO "$hf/databricks/databricks-dolly-15k/resolve/main/databricks-dolly-15k.jsonl"
curl -sSLO "$hf/OpenAssistant/oasst1/resolve/main/2023-04-12_oasst_ready.messages.jsonl.gz"
curl -sSLO "$hf/allenai/c4/resolve/main/en/c4-validation.00000-of-00008.json.gz"
curl -sSLO https://www.unicode.org/Public/security/latest/confusables.txt
ls -l
