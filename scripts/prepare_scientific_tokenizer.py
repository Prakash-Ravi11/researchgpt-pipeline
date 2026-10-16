"""Export the installed Qwen2 tokenizer locally; no inference or downloads."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
import requests

def prepare(base_url, model, output):
    if urlparse(base_url).hostname not in {"localhost","127.0.0.1","::1"}:
        raise ValueError("Tokenizer export must use the local model service")
    if output.exists():
        raise ValueError("Choose a fresh tokenizer directory")
    with requests.Session() as session:
        tags=session.get(base_url.rstrip("/")+"/api/tags",timeout=10)
        tags.raise_for_status()
        selected=next(x for x in tags.json()["models"] if x["name"]==model)
        response=session.post(base_url.rstrip("/")+"/api/show",
                              json={"model":model,"verbose":True},timeout=30)
        response.raise_for_status()
        metadata=response.json()["model_info"]
    if metadata.get("tokenizer.ggml.pre")!="qwen2" or metadata.get("tokenizer.ggml.model")!="gpt2":
        raise ValueError("Installed tokenizer is not the supported Qwen2 BPE")
    from transformers import Qwen2Tokenizer
    from tokenizers import AddedToken
    tokens=metadata["tokenizer.ggml.tokens"]
    vocab={text:index for index,text in enumerate(tokens)}
    if len(vocab)!=len(tokens):
        raise ValueError("Duplicate vocabulary strings cannot be exported faithfully")
    tokenizer=Qwen2Tokenizer(vocab=vocab,merges=[tuple(x.split(" ")) for x in
        metadata["tokenizer.ggml.merges"]],bos_token=None,
        eos_token=tokens[metadata["tokenizer.ggml.eos_token_id"]],
        pad_token=tokens[metadata["tokenizer.ggml.padding_token_id"]])
    special=[AddedToken(token,special=True,normalized=False) for token,kind in
             zip(tokens,metadata["tokenizer.ggml.token_type"]) if kind==3]
    tokenizer.add_tokens(special)
    # Verify every installed ID, including control tokens, before saving.
    if any(tokenizer.convert_tokens_to_ids(text)!=index for index,text in enumerate(tokens)):
        raise ValueError("Export changed installed token IDs")
    output.mkdir(parents=True)
    tokenizer.save_pretrained(output)
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}
    record={"model":model,"model_digest":selected["digest"],"service":base_url,
            "method":"installed_metadata_with_existing_Qwen2Tokenizer",
            "token_count":len(tokens),"merge_count":len(metadata["tokenizer.ggml.merges"]),
            "all_token_ids_verified":True,"inference_requests":0,"files":files}
    (output/"export_manifest.json").write_text(json.dumps(record,indent=2),encoding="utf-8")
    return record

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url",default="http://localhost:11434")
    parser.add_argument("--model",default="qwen2.5:7b")
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(prepare(args.base_url,args.model,args.output)))
if __name__=="__main__":main()
